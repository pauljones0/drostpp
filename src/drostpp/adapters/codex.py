"""Codex CLI adapter using existing local OAuth/CODEX_HOME configuration and MCP forwarding."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
from typing import Any

from ..config import CodexProviderConfig
from ..models import AttemptResult, ErrorKind
from ..supervision import ProcessSupervisor
from .base import (
    AttemptContext,
    WORKER_OUTPUT_JSON_SCHEMA,
    classify_error_text,
    parse_worker_output,
)

_BARE_TOML_KEY_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _toml_key(key: str) -> str:
    return key if _BARE_TOML_KEY_RE.fullmatch(key) else json.dumps(key)


def toml_literal(value: Any) -> str:
    """Serialize Python primitives/lists/dicts into Codex `-c key=value` TOML literal syntax."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(toml_literal(item) for item in value) + "]"
    if isinstance(value, dict):
        items = [f"{_toml_key(str(k))} = {toml_literal(v)}" for k, v in sorted(value.items())]
        return "{" + ", ".join(items) + "}"
    raise TypeError(f"unsupported TOML literal type: {type(value)!r}")


class CodexAdapter:
    """Invokes `codex exec` non-interactively with structured output and MCP server injection."""

    def __init__(
        self,
        config: CodexProviderConfig,
        *,
        supervisor: ProcessSupervisor | None = None,
        heartbeat_interval: float = 15.0,
    ) -> None:
        self.config = config
        self.supervisor = supervisor or ProcessSupervisor()
        self.heartbeat_interval = heartbeat_interval

    def build_argv(
        self,
        ctx: AttemptContext,
        schema_path: Path,
        last_message_path: Path,
    ) -> list[str]:
        workdir = ctx.workspace_dir or ctx.attempt_dir
        argv = [
            self.config.binary,
            "exec",
            "--ephemeral",
            "--skip-git-repo-check",
            "--json",
            "--color",
            "never",
            "-s",
            self.config.sandbox,
            "-C",
            str(workdir),
            "--output-schema",
            str(schema_path),
            "-o",
            str(last_message_path),
        ]
        model = ctx.route.model or self.config.default_model
        if model:
            argv.extend(["-m", model])
        profile = ctx.route.options.get("profile") or self.config.profile
        if profile:
            argv.extend(["-p", str(profile)])

        merged_cfg: dict[str, Any] = dict(self.config.extra_config)
        route_cfg = ctx.route.options.get("config")
        if isinstance(route_cfg, dict):
            merged_cfg.update(route_cfg)
        for key, value in sorted(merged_cfg.items()):
            argv.extend(["-c", f"{key}={toml_literal(value)}"])

        for srv in ctx.mcp_servers:
            if not srv.enabled:
                continue
            prefix = f"mcp_servers.{srv.name}"
            argv.extend(["-c", f"{prefix}.command={toml_literal(srv.command)}"])
            if srv.args:
                argv.extend(["-c", f"{prefix}.args={toml_literal(srv.args)}"])
            if srv.env:
                argv.extend(["-c", f"{prefix}.env={toml_literal(srv.env)}"])
            argv.extend(["-c", f"{prefix}.tool_timeout_sec={toml_literal(int(srv.timeout_seconds))}"])

        argv.append("-")
        return argv

    def execute(self, ctx: AttemptContext) -> AttemptResult:
        ctx.attempt_dir.mkdir(parents=True, exist_ok=True)
        schema_path = ctx.attempt_dir / "output_schema.json"
        last_message_path = ctx.attempt_dir / "last_message.txt"
        schema_path.write_text(
            json.dumps(WORKER_OUTPUT_JSON_SCHEMA, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        argv = self.build_argv(ctx, schema_path, last_message_path)
        env = dict(os.environ)
        env.update(ctx.env)
        if self.config.codex_home:
            env["CODEX_HOME"] = self.config.codex_home

        usage = {"input": 0, "output": 0, "total": 0}
        agent_messages: list[str] = []
        stream_errors: list[str] = []
        token_budget_exceeded = False

        def _on_line(line: str) -> None:
            nonlocal token_budget_exceeded
            text = line.strip()
            if not text.startswith("{"):
                return
            try:
                ev = json.loads(text)
            except json.JSONDecodeError:
                return
            if not isinstance(ev, dict):
                return

            u = ev.get("usage")
            if isinstance(u, dict):
                in_tok = int(u.get("input_tokens", 0) or 0)
                out_tok = int(u.get("output_tokens", 0) or 0)
                tot_tok = int(u.get("total_tokens", in_tok + out_tok) or 0)
                usage["input"] += in_tok
                usage["output"] += out_tok
                usage["total"] += tot_tok
                if usage["total"] > ctx.budget.max_tokens:
                    token_budget_exceeded = True
                    ctx.cancel_event.set()

            ev_type = str(ev.get("type", ""))
            if ev_type == "item.completed":
                item = ev.get("item")
                if isinstance(item, dict) and item.get("type") == "agent_message":
                    msg_text = item.get("text")
                    if isinstance(msg_text, str) and msg_text.strip():
                        agent_messages.append(msg_text)
            elif ev_type in {"error", "turn.failed"}:
                msg = ev.get("message") or (
                    ev.get("error", {}).get("message")
                    if isinstance(ev.get("error"), dict)
                    else None
                )
                if isinstance(msg, str) and msg.strip():
                    stream_errors.append(msg.strip())

        def _on_spawn(pid: int, pgid: int) -> None:
            if ctx.on_runtime_attached is not None:
                ctx.on_runtime_attached(pid, pgid, None)

        def _on_hb() -> None:
            if ctx.on_heartbeat is not None:
                ctx.on_heartbeat(usage["input"], usage["output"], usage["total"])

        try:
            proc_res = self.supervisor.run(
                argv,
                cwd=ctx.workspace_dir or ctx.attempt_dir,
                env=env,
                stdin_text=ctx.prompt,
                wall_timeout=ctx.budget.max_wall_seconds,
                max_output_bytes=ctx.budget.max_output_bytes,
                max_memory_mb=ctx.budget.max_memory_mb,
                max_disk_bytes=ctx.budget.max_disk_bytes,
                disk_watch_dir=ctx.attempt_dir,
                cancel_event=ctx.cancel_event,
                on_spawn=_on_spawn,
                on_stdout_line=_on_line,
                on_heartbeat=_on_hb,
                heartbeat_interval=self.heartbeat_interval,
                stdout_log=ctx.attempt_dir / "codex.stdout.jsonl",
                stderr_log=ctx.attempt_dir / "codex.stderr.log",
            )
        except OSError as exc:
            return AttemptResult(
                success=False,
                error_kind=ErrorKind.HARD_ERROR,
                error_message=f"failed to launch codex binary {self.config.binary!r}: {exc}",
            )

        if token_budget_exceeded:
            return AttemptResult(
                success=False,
                input_tokens=usage["input"],
                output_tokens=usage["output"],
                total_tokens=usage["total"],
                error_kind=ErrorKind.BUDGET_EXCEEDED,
                error_message=f"task token budget exceeded ({usage['total']} > {ctx.budget.max_tokens})",
            )

        if proc_res.timed_out:
            return AttemptResult(
                success=False,
                input_tokens=usage["input"],
                output_tokens=usage["output"],
                total_tokens=usage["total"],
                error_kind=ErrorKind.TIMEOUT,
                error_message=proc_res.kill_reason or "codex attempt timed out",
                timed_out=True,
            )

        if proc_res.cancelled:
            return AttemptResult(
                success=False,
                input_tokens=usage["input"],
                output_tokens=usage["output"],
                total_tokens=usage["total"],
                error_kind=ErrorKind.HARD_ERROR,
                error_message="codex attempt cancelled",
                cancelled=True,
            )

        if proc_res.kill_reason:
            return AttemptResult(
                success=False,
                input_tokens=usage["input"],
                output_tokens=usage["output"],
                total_tokens=usage["total"],
                error_kind=ErrorKind.BUDGET_EXCEEDED,
                error_message=proc_res.kill_reason,
            )

        if proc_res.returncode != 0:
            err_msg = "; ".join(stream_errors) or proc_res.stderr.strip() or f"codex exited {proc_res.returncode}"
            return AttemptResult(
                success=False,
                input_tokens=usage["input"],
                output_tokens=usage["output"],
                total_tokens=usage["total"],
                error_kind=classify_error_text(err_msg + "\n" + proc_res.stderr),
                error_message=err_msg[:1500],
            )

        final_text = ""
        if last_message_path.is_file():
            final_text = last_message_path.read_text(encoding="utf-8", errors="replace").strip()
        if not final_text and agent_messages:
            final_text = agent_messages[-1]
        if not final_text:
            final_text = proc_res.stdout

        output = parse_worker_output(final_text)
        return AttemptResult(
            success=True,
            output=output,
            input_tokens=usage["input"],
            output_tokens=usage["output"],
            total_tokens=usage["total"],
            error_kind=ErrorKind.NONE,
            metadata={"duration_seconds": proc_res.duration_seconds, "peak_rss_mb": proc_res.peak_rss_mb},
        )
