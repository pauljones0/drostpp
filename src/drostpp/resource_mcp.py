"""Minimal stdio MCP facade for the durable managed-container broker."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from .config import config_from_dict
from .resources import ResourceManager
from .store import SQLiteStore

_TOOLS: list[dict[str, Any]] = [
    {
        "name": "resource_start",
        "description": (
            "Start a RAM/PID/disk/log-capped Docker container owned by this attempt. "
            "Starting an already-live key borrows it instead. Published ports bind only to 127.0.0.1."
        ),
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["key", "image"],
            "properties": {
                "key": {"type": "string"},
                "image": {"type": "string"},
                "command": {"type": "array", "items": {"type": "string"}},
                "env": {"type": "object", "additionalProperties": {"type": "string"}},
                "publish_container_ports": {
                    "type": "array",
                    "items": {"type": "integer", "minimum": 1, "maximum": 65535},
                },
            },
        },
    },
    {
        "name": "resource_borrow",
        "description": "Borrow and renew a live managed container by key.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["key"],
            "properties": {"key": {"type": "string"}},
        },
    },
    {
        "name": "resource_exec",
        "description": "Borrow a managed container and run one bounded command inside it.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["key", "command"],
            "properties": {
                "key": {"type": "string"},
                "command": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                },
                "timeout_seconds": {"type": "number", "minimum": 0.1, "maximum": 3600},
            },
        },
    },
    {
        "name": "resource_release",
        "description": (
            "Release this attempt's borrow. The container is removed immediately if no borrower remains."
        ),
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["key"],
            "properties": {"key": {"type": "string"}},
        },
    },
    {
        "name": "resource_list",
        "description": "List this run's managed containers and lifecycle status.",
        "inputSchema": {"type": "object", "additionalProperties": False, "properties": {}},
    },
]


class ResourceMcpServer:
    def __init__(self) -> None:
        required = {
            name: os.environ.get(name, "")
            for name in (
                "DROSTPP_STATE_DIR",
                "DROSTPP_RUN_ID",
                "DROSTPP_TASK_ID",
                "DROSTPP_ATTEMPT_ID",
                "DROSTPP_GENERATION",
            )
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise RuntimeError(f"missing resource broker context: {', '.join(missing)}")
        self.run_id = required["DROSTPP_RUN_ID"]
        self.task_id = required["DROSTPP_TASK_ID"]
        self.attempt_id = required["DROSTPP_ATTEMPT_ID"]
        self.generation = int(required["DROSTPP_GENERATION"])
        self.store = SQLiteStore(Path(required["DROSTPP_STATE_DIR"]) / "drostpp.db")
        run = self.store.get_run(self.run_id)
        if run is None:
            raise RuntimeError(f"unknown resource broker run: {self.run_id}")
        cfg = config_from_dict(json.loads(run.config_json))
        if not cfg.container.enabled:
            raise RuntimeError("managed containers are disabled for this run")
        self.manager = ResourceManager(
            self.store,
            cfg.container,
            attempt_lease_seconds=cfg.run.lease_seconds,
            min_available_memory_mb=cfg.budgets.min_available_memory_mb,
            min_free_disk_bytes=cfg.budgets.min_free_disk_bytes,
        )

    def close(self) -> None:
        self.store.close()

    def call(self, name: str, arguments: dict[str, Any]) -> Any:
        if name == "resource_start":
            env_raw = arguments.get("env") or {}
            if not isinstance(env_raw, dict):
                raise ValueError("env must be an object")
            resource = self.manager.start_container(
                run_id=self.run_id,
                task_id=self.task_id,
                attempt_id=self.attempt_id,
                generation=self.generation,
                resource_key=str(arguments.get("key", "")),
                image=str(arguments.get("image", "")),
                command=[str(item) for item in arguments.get("command") or []],
                env={str(key): str(value) for key, value in env_raw.items()},
                publish_container_ports=[
                    int(port) for port in arguments.get("publish_container_ports") or []
                ],
            )
            return self.manager.describe(resource)
        if name == "resource_borrow":
            resource = self.manager.borrow_container(
                run_id=self.run_id,
                task_id=self.task_id,
                attempt_id=self.attempt_id,
                generation=self.generation,
                resource_key=str(arguments.get("key", "")),
            )
            return self.manager.describe(resource)
        if name == "resource_exec":
            resource, returncode, stdout, stderr = self.manager.exec_container(
                run_id=self.run_id,
                task_id=self.task_id,
                attempt_id=self.attempt_id,
                generation=self.generation,
                resource_key=str(arguments.get("key", "")),
                command=[str(item) for item in arguments.get("command") or []],
                timeout=min(3600.0, max(0.1, float(arguments.get("timeout_seconds", 300.0)))),
            )
            return {
                "resource_key": resource.resource_key,
                "returncode": returncode,
                "stdout": stdout,
                "stderr": stderr,
            }
        if name == "resource_release":
            return self.manager.release_container(
                self.attempt_id, str(arguments.get("key", ""))
            )
        if name == "resource_list":
            return [
                self.manager.describe(resource)
                for resource in self.store.list_managed_resources(self.run_id)
            ]
        raise ValueError(f"unknown tool: {name}")


def _response(req_id: Any, result: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": req_id, "result": result}) + "\n")
    sys.stdout.flush()


def main() -> int:
    try:
        server = ResourceMcpServer()
    except Exception as exc:  # noqa: BLE001 - RPC boundary must fail closed with stderr context.
        sys.stderr.write(f"resource MCP initialization failed: {exc}\n")
        return 1
    try:
        for line in sys.stdin:
            request: Any = None
            try:
                request = json.loads(line)
                if not isinstance(request, dict):
                    continue
                req_id = request.get("id")
                method = request.get("method")
                if req_id is None:
                    continue
                if method == "initialize":
                    _response(
                        req_id,
                        {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {"tools": {}},
                            "serverInfo": {"name": "drostpp-resource-broker", "version": "0.1.0"},
                        },
                    )
                elif method == "tools/list":
                    _response(req_id, {"tools": _TOOLS})
                elif method == "tools/call":
                    params = request.get("params") or {}
                    name = str(params.get("name") or "")
                    arguments = params.get("arguments") or {}
                    if not isinstance(arguments, dict):
                        raise ValueError("tool arguments must be an object")
                    try:
                        value = server.call(name, arguments)
                        _response(
                            req_id,
                            {
                                "content": [
                                    {
                                        "type": "text",
                                        "text": json.dumps(value, indent=2, sort_keys=True),
                                    }
                                ],
                            },
                        )
                    except Exception as exc:  # noqa: BLE001 - tool errors are MCP results.
                        _response(
                            req_id,
                            {
                                "content": [{"type": "text", "text": f"{type(exc).__name__}: {exc}"}],
                                "isError": True,
                            },
                        )
                else:
                    _response(req_id, {})
            except Exception as exc:  # noqa: BLE001 - malformed requests must not kill the server.
                req_id = request.get("id") if isinstance(request, dict) else None
                if req_id is not None:
                    _response(
                        req_id,
                        {
                            "content": [{"type": "text", "text": f"{type(exc).__name__}: {exc}"}],
                            "isError": True,
                        },
                    )
    finally:
        server.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
