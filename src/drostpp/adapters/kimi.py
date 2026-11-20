"""Kimi adapters: Moonshot/Kimi OpenAI-compatible HTTP API with MCP tool bridge, plus Kimi CLI."""

from __future__ import annotations

import json
import os
import time
from typing import Any
import urllib.error
import urllib.request

from ..config import KimiProviderConfig
from ..integrations.mcp import McpError, McpStdioClient
from ..models import AttemptResult, ErrorKind
from ..supervision import ProcessSupervisor
from .base import AttemptContext, classify_error_text, parse_worker_output


def _sanitize_tool_name(server: str, tool: str) -> str:
    raw = f"{server}__{tool}"
    return "".join(ch if (ch.isalnum() or ch in {"_", "-"}) else "_" for ch in raw)[:64]


class KimiApiAdapter:
    """Runs bounded tool-calling chat completions against Kimi's OpenAI-compatible endpoint."""

    def __init__(self, config: KimiProviderConfig) -> None:
        self.config = config

    def _resolve_api_key(self) -> str | None:
        return os.environ.get(self.config.api_key_env) or os.environ.get("MOONSHOT_API_KEY")

    def execute(self, ctx: AttemptContext) -> AttemptResult:
        api_key = self._resolve_api_key()
        if not api_key:
            return AttemptResult(
                success=False,
                error_kind=ErrorKind.HARD_ERROR,
                error_message=f"missing Kimi API key in env {self.config.api_key_env} or MOONSHOT_API_KEY",
            )

        ctx.attempt_dir.mkdir(parents=True, exist_ok=True)
        model = ctx.route.model or self.config.default_model
        started = time.monotonic()
        clients: list[McpStdioClient] = []
        tool_dispatch: dict[str, tuple[McpStdioClient, str]] = {}
        openai_tools: list[dict[str, Any]] = []

        try:
            for srv in ctx.mcp_servers:
                if not srv.enabled:
                    continue
                client = McpStdioClient(srv, spill_dir=ctx.attempt_dir / "mcp_spill")
                client.start()
                clients.append(client)
                for tool in client.list_tools():
                    fn_name = _sanitize_tool_name(srv.name, tool["name"])
                    tool_dispatch[fn_name] = (client, tool["name"])
                    openai_tools.append(
                        {
                            "type": "function",
                            "function": {
                                "name": fn_name,
                                "description": tool["description"][:1024],
                                "parameters": tool["inputSchema"],
                            },
                        }
                    )

            messages: list[dict[str, Any]] = [
                {
                    "role": "system",
                    "content": (
                        "Return your final answer strictly as JSON matching the schema in the prompt. "
                        "Use available tools when needed; never invent observations."
                    ),
                },
                {"role": "user", "content": ctx.prompt},
            ]

            in_tokens = 0
            out_tokens = 0
            tot_tokens = 0

            for _turn in range(self.config.max_tool_turns):
                if ctx.cancel_event.is_set():
                    return AttemptResult(
                        success=False,
                        input_tokens=in_tokens,
                        output_tokens=out_tokens,
                        total_tokens=tot_tokens,
                        error_kind=ErrorKind.HARD_ERROR,
                        error_message="kimi attempt cancelled",
                        cancelled=True,
                    )

                elapsed = time.monotonic() - started
                remaining = ctx.budget.max_wall_seconds - elapsed
                if remaining <= 0:
                    return AttemptResult(
                        success=False,
                        input_tokens=in_tokens,
                        output_tokens=out_tokens,
                        total_tokens=tot_tokens,
                        error_kind=ErrorKind.TIMEOUT,
                        error_message=f"kimi attempt exceeded wall timeout ({ctx.budget.max_wall_seconds}s)",
                        timed_out=True,
                    )

                payload: dict[str, Any] = {
                    "model": model,
                    "messages": messages,
                    "response_format": {"type": "json_object"},
                }
                if openai_tools:
                    payload["tools"] = openai_tools

                resp_data, err = self._post_with_retry(
                    payload,
                    api_key=api_key,
                    timeout=min(self.config.timeout_seconds, remaining),
                    cancel_event=ctx.cancel_event,
                )
                if err is not None:
                    err_kind, err_msg = err
                    return AttemptResult(
                        success=False,
                        input_tokens=in_tokens,
                        output_tokens=out_tokens,
                        total_tokens=tot_tokens,
                        error_kind=err_kind,
                        error_message=err_msg,
                    )

                assert resp_data is not None
                usage = resp_data.get("usage")
                if isinstance(usage, dict):
                    p_tok = int(usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0)
                    c_tok = int(usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0)
                    t_tok = int(usage.get("total_tokens", p_tok + c_tok) or 0)
                    in_tokens += p_tok
                    out_tokens += c_tok
                    tot_tokens += t_tok

                if ctx.on_heartbeat is not None:
                    ctx.on_heartbeat(in_tokens, out_tokens, tot_tokens)

                if tot_tokens > ctx.budget.max_tokens:
                    return AttemptResult(
                        success=False,
                        input_tokens=in_tokens,
                        output_tokens=out_tokens,
                        total_tokens=tot_tokens,
                        error_kind=ErrorKind.BUDGET_EXCEEDED,
                        error_message=f"task token budget exceeded ({tot_tokens} > {ctx.budget.max_tokens})",
                    )

                choices = resp_data.get("choices") or []
                if not choices:
                    return AttemptResult(
                        success=False,
                        input_tokens=in_tokens,
                        output_tokens=out_tokens,
                        total_tokens=tot_tokens,
                        error_kind=ErrorKind.HARD_ERROR,
                        error_message="kimi response contained empty choices",
                    )

                msg = choices[0].get("message") or {}
                tool_calls = msg.get("tool_calls") or []
                if tool_calls:
                    messages.append(
                        {
                            "role": "assistant",
                            "content": msg.get("content") or "",
                            "tool_calls": tool_calls,
                        }
                    )
                    for tc in tool_calls:
                        tc_id = str(tc.get("id") or "")
                        fn = tc.get("function") or {}
                        fn_name = str(fn.get("name") or "")
                        raw_args = fn.get("arguments") or "{}"
                        try:
                            args_obj = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
                        except json.JSONDecodeError:
                            args_obj = {}

                        target = tool_dispatch.get(fn_name)
                        if target is None:
                            tool_output = f"error: unknown tool {fn_name}"
                        else:
                            client, orig_name = target
                            try:
                                tool_output = client.call_tool(orig_name, args_obj)
                            except McpError as exc:
                                tool_output = f"error executing {orig_name}: {exc}"
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc_id,
                                "content": tool_output,
                            }
                        )
                    continue

                content = str(msg.get("content") or "")
                parsed = parse_worker_output(content)
                return AttemptResult(
                    success=True,
                    output=parsed,
                    input_tokens=in_tokens,
                    output_tokens=out_tokens,
                    total_tokens=tot_tokens,
                    error_kind=ErrorKind.NONE,
                )

            return AttemptResult(
                success=False,
                input_tokens=in_tokens,
                output_tokens=out_tokens,
                total_tokens=tot_tokens,
                error_kind=ErrorKind.HARD_ERROR,
                error_message=f"kimi exceeded max_tool_turns ({self.config.max_tool_turns}) without final response",
            )
        except McpError as exc:
            return AttemptResult(
                success=False,
                error_kind=ErrorKind.HARD_ERROR,
                error_message=str(exc),
            )
        finally:
            for client in clients:
                client.close()

    def _post_with_retry(
        self,
        payload: dict[str, Any],
        *,
        api_key: str,
        timeout: float,
        cancel_event: Any,
    ) -> tuple[dict[str, Any] | None, tuple[ErrorKind, str] | None]:
        url = f"{self.config.base_url}/chat/completions"
        body = json.dumps(payload).encode("utf-8")
        last_err: tuple[ErrorKind, str] = (ErrorKind.HARD_ERROR, "unknown HTTP error")

        for attempt in range(3):
            if cancel_event.is_set():
                return None, (ErrorKind.HARD_ERROR, "cancelled")
            req = urllib.request.Request(
                url,
                data=body,
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=max(1.0, timeout)) as resp:
                    raw = resp.read().decode("utf-8", errors="replace")
                decoded = json.loads(raw)
                if not isinstance(decoded, dict):
                    return None, (ErrorKind.HARD_ERROR, "non-object JSON from Kimi API")
                return decoded, None
            except urllib.error.HTTPError as exc:
                err_body = ""
                try:
                    err_body = exc.read().decode("utf-8", errors="replace")[:500]
                except Exception:
                    pass
                msg = f"HTTP {exc.code}: {err_body or exc.reason}"
                if exc.code == 429:
                    last_err = (ErrorKind.QUOTA, msg)
                elif exc.code in {500, 502, 503, 504}:
                    last_err = (ErrorKind.TRANSIENT, msg)
                else:
                    return None, (ErrorKind.HARD_ERROR, msg)
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_err = (ErrorKind.TRANSIENT, f"network error: {exc}")

            if attempt < 2:
                time.sleep(min(0.5 * (2**attempt), 2.0))

        return None, last_err


class KimiCliAdapter:
    """Invokes local `kimi -p ... --output-format stream-json --auto` via ProcessSupervisor."""

    def __init__(
        self,
        config: KimiProviderConfig,
        *,
        supervisor: ProcessSupervisor | None = None,
        heartbeat_interval: float = 15.0,
    ) -> None:
        self.config = config
        self.supervisor = supervisor or ProcessSupervisor()
        self.heartbeat_interval = heartbeat_interval

    def build_argv(self, ctx: AttemptContext) -> list[str]:
        argv = [
            self.config.cli_binary,
            "-p",
            ctx.prompt,
            "--output-format",
            "stream-json",
            "--auto",
        ]
        model = ctx.route.model or self.config.default_model
        if model:
            argv.extend(["-m", model])
        return argv

    def execute(self, ctx: AttemptContext) -> AttemptResult:
        ctx.attempt_dir.mkdir(parents=True, exist_ok=True)
        argv = self.build_argv(ctx)
        usage = {"input": 0, "output": 0, "total": 0}
        assistant_parts: list[str] = []
        token_budget_exceeded = False

        def _on_line(line: str) -> None:
            nonlocal token_budget_exceeded
            s = line.strip()
            if not s.startswith("{"):
                return
            try:
                ev = json.loads(s)
            except json.JSONDecodeError:
                return
            if not isinstance(ev, dict):
                return
            u = ev.get("usage")
            if isinstance(u, dict):
                in_tok = int(u.get("input_tokens", u.get("prompt_tokens", 0)) or 0)
                out_tok = int(u.get("output_tokens", u.get("completion_tokens", 0)) or 0)
                tot_tok = int(u.get("total_tokens", in_tok + out_tok) or 0)
                usage["input"] += in_tok
                usage["output"] += out_tok
                usage["total"] += tot_tok
                if usage["total"] > ctx.budget.max_tokens:
                    token_budget_exceeded = True
                    ctx.cancel_event.set()
            content = ev.get("content") or ev.get("text")
            if isinstance(content, str) and ev.get("role", "assistant") == "assistant":
                assistant_parts.append(content)

        def _on_spawn(pid: int, pgid: int) -> None:
            if ctx.on_runtime_attached is not None:
                ctx.on_runtime_attached(pid, pgid, None)

        def _on_hb() -> None:
            if ctx.on_heartbeat is not None:
                ctx.on_heartbeat(usage["input"], usage["output"], usage["total"])

        try:
            env = dict(os.environ)
            env.update(ctx.env)
            proc_res = self.supervisor.run(
                argv,
                cwd=ctx.workspace_dir or ctx.attempt_dir,
                env=env,
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
                stdout_log=ctx.attempt_dir / "kimi.stdout.jsonl",
                stderr_log=ctx.attempt_dir / "kimi.stderr.log",
            )
        except OSError as exc:
            return AttemptResult(
                success=False,
                error_kind=ErrorKind.HARD_ERROR,
                error_message=f"failed to launch kimi CLI {self.config.cli_binary!r}: {exc}",
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
                error_message=proc_res.kill_reason or "kimi CLI timed out",
                timed_out=True,
            )
        if proc_res.cancelled:
            return AttemptResult(
                success=False,
                input_tokens=usage["input"],
                output_tokens=usage["output"],
                total_tokens=usage["total"],
                error_kind=ErrorKind.HARD_ERROR,
                error_message="kimi CLI cancelled",
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
            err_msg = proc_res.stderr.strip() or f"kimi exited {proc_res.returncode}"
            return AttemptResult(
                success=False,
                input_tokens=usage["input"],
                output_tokens=usage["output"],
                total_tokens=usage["total"],
                error_kind=classify_error_text(err_msg),
                error_message=err_msg[:1500],
            )

        raw_text = "".join(assistant_parts).strip() or proc_res.stdout
        return AttemptResult(
            success=True,
            output=parse_worker_output(raw_text),
            input_tokens=usage["input"],
            output_tokens=usage["output"],
            total_tokens=usage["total"],
            error_kind=ErrorKind.NONE,
        )
