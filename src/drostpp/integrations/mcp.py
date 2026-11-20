"""Minimal JSON-RPC 2.0 stdio MCP client with timeouts, output caps, and process-group teardown."""

from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
from typing import Any
import uuid

from ..models import McpServerConfig, OrchestratorError
from ..supervision import terminate_process_group


class McpError(OrchestratorError):
    """Raised when an MCP server fails initialization, times out, or returns an RPC error."""


class McpStdioClient:
    """Line-delimited JSON-RPC 2.0 client over stdio for external MCP servers such as drost-mcp."""

    def __init__(
        self,
        config: McpServerConfig,
        *,
        spill_dir: Path | None = None,
    ) -> None:
        self.config = config
        self.spill_dir = spill_dir
        self._proc: subprocess.Popen[bytes] | None = None
        self._pgid: int = 0
        self._next_id = 1
        self._id_lock = threading.Lock()
        self._call_lock = threading.Lock()
        self._responses: queue.Queue[dict[str, Any] | Exception] = queue.Queue()
        self._stderr_tail: list[str] = []
        self._out_thread: threading.Thread | None = None
        self._err_thread: threading.Thread | None = None
        self._closed = False

    def __enter__(self) -> McpStdioClient:
        self.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def start(self) -> dict[str, Any]:
        if self._proc is not None:
            return {}
        env = dict(os.environ)
        env.update(self.config.env)
        argv = [self.config.command, *self.config.args]
        self._proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            start_new_session=True,
        )
        try:
            self._pgid = os.getpgid(self._proc.pid)
        except OSError:
            self._pgid = self._proc.pid

        self._out_thread = threading.Thread(target=self._read_stdout, daemon=True)
        self._err_thread = threading.Thread(target=self._read_stderr, daemon=True)
        self._out_thread.start()
        self._err_thread.start()

        try:
            init_res = self._request(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "drost++", "version": "0.1.0"},
                },
                timeout=self.config.timeout_seconds,
            )
            self._notify("notifications/initialized", {})
            return init_res
        except Exception:
            self.close()
            raise

    def _read_stdout(self) -> None:
        assert self._proc is not None and self._proc.stdout is not None
        try:
            for raw in self._proc.stdout:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(msg, dict) and "id" in msg:
                    self._responses.put(msg)
        except Exception as exc:
            self._responses.put(exc)
        finally:
            self._responses.put(EOFError("MCP server closed stdout"))

    def _read_stderr(self) -> None:
        assert self._proc is not None and self._proc.stderr is not None
        try:
            for raw in self._proc.stderr:
                line = raw.decode("utf-8", errors="replace").rstrip()
                if line:
                    self._stderr_tail.append(line[:500])
                    if len(self._stderr_tail) > 50:
                        del self._stderr_tail[0]
        except Exception:
            pass

    def _alloc_id(self) -> int:
        with self._id_lock:
            val = self._next_id
            self._next_id += 1
            return val

    def _send_json(self, payload: dict[str, Any]) -> None:
        if self._proc is None or self._proc.stdin is None or self._closed:
            raise McpError(f"MCP server {self.config.name} is not running")
        data = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
        try:
            self._proc.stdin.write(data)
            self._proc.stdin.flush()
        except OSError as exc:
            raise McpError(f"failed writing to MCP server {self.config.name}: {exc}") from exc

    def _notify(self, method: str, params: dict[str, Any]) -> None:
        self._send_json({"jsonrpc": "2.0", "method": method, "params": params})

    def _request(
        self,
        method: str,
        params: dict[str, Any],
        *,
        timeout: float,
    ) -> dict[str, Any]:
        with self._call_lock:
            req_id = self._alloc_id()
            self._send_json(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "method": method,
                    "params": params,
                }
            )
            deadline = time.monotonic() + max(0.5, timeout)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    stderr_ctx = "; ".join(self._stderr_tail[-5:])
                    self.close()
                    raise McpError(
                        f"MCP call {self.config.name}.{method} timed out after {timeout}s"
                        + (f" (stderr: {stderr_ctx})" if stderr_ctx else "")
                    )
                try:
                    item = self._responses.get(timeout=min(remaining, 0.25))
                except queue.Empty:
                    continue

                if isinstance(item, Exception):
                    stderr_ctx = "; ".join(self._stderr_tail[-5:])
                    raise McpError(
                        f"MCP server {self.config.name} terminated during {method}: {item}"
                        + (f" (stderr: {stderr_ctx})" if stderr_ctx else "")
                    )
                if item.get("id") != req_id:
                    continue
                if "error" in item and item["error"] is not None:
                    raise McpError(f"MCP error from {self.config.name}.{method}: {item['error']}")
                result = item.get("result")
                return result if isinstance(result, dict) else {"value": result}

    def list_tools(self) -> list[dict[str, Any]]:
        result = self._request("tools/list", {}, timeout=self.config.timeout_seconds)
        tools = result.get("tools", [])
        if not isinstance(tools, list):
            return []
        normalized: list[dict[str, Any]] = []
        for tool in tools:
            if not isinstance(tool, dict) or not tool.get("name"):
                continue
            normalized.append(
                {
                    "name": str(tool["name"]),
                    "description": str(tool.get("description", "")),
                    "inputSchema": tool.get("inputSchema")
                    or {"type": "object", "properties": {}},
                }
            )
        return normalized

    def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> str:
        eff_timeout = timeout if timeout is not None else self.config.timeout_seconds
        result = self._request(
            "tools/call",
            {"name": name, "arguments": arguments or {}},
            timeout=eff_timeout,
        )
        rendered = self._format_tool_result(result)
        return self._cap_text(name, rendered)

    def _format_tool_result(self, result: dict[str, Any]) -> str:
        if "structuredContent" in result and result["structuredContent"] is not None:
            return json.dumps(result["structuredContent"], indent=2, sort_keys=True)
        content = result.get("content")
        if isinstance(content, list):
            chunks: list[str] = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text" and isinstance(block.get("text"), str):
                        chunks.append(block["text"])
                    else:
                        chunks.append(json.dumps(block, sort_keys=True))
                else:
                    chunks.append(str(block))
            return "\n".join(chunks)
        return json.dumps(result, indent=2, sort_keys=True)

    def _cap_text(self, tool_name: str, text: str) -> str:
        raw = text.encode("utf-8", errors="replace")
        limit = self.config.max_result_bytes
        if len(raw) <= limit:
            return text
        spill_note = ""
        if self.spill_dir is not None:
            try:
                self.spill_dir.mkdir(parents=True, exist_ok=True)
                spill_path = self.spill_dir / f"mcp_{tool_name}_{uuid.uuid4().hex[:8]}.txt"
                spill_path.write_bytes(raw)
                spill_note = f" (full output saved to {spill_path})"
            except OSError:
                pass
        prefix = raw[: max(256, limit - 256)].decode("utf-8", errors="ignore")
        return f"{prefix}\n...[truncated from {len(raw)} bytes to {limit} bytes{spill_note}]"

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        proc = self._proc
        self._proc = None
        if proc is None:
            return
        if proc.stdin is not None:
            try:
                proc.stdin.close()
            except OSError:
                pass
        terminate_process_group(self._pgid, proc=proc, grace_seconds=1.0, hard_wait_seconds=2.0)
        if self._out_thread is not None:
            self._out_thread.join(timeout=1.0)
        if self._err_thread is not None:
            self._err_thread.join(timeout=1.0)
        for pipe in (proc.stdout, proc.stderr):
            if pipe is not None:
                try:
                    pipe.close()
                except OSError:
                    pass
