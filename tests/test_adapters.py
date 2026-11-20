"""Tests for Codex CLI adapter, Kimi API/CLI adapters, TOML escaping, and ModelRouter failover."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import sys
import threading

from drostpp.adapters.base import AttemptContext
from drostpp.adapters.codex import CodexAdapter, toml_literal
from drostpp.adapters.kimi import KimiApiAdapter, KimiCliAdapter
from drostpp.adapters.mock import MockAdapter
from drostpp.config import CodexProviderConfig, KimiProviderConfig, OrchestratorConfig, RoutingConfig
from drostpp.coordinator import Coordinator
from drostpp.models import (
    AttemptRecord,
    AttemptResult,
    AttemptStatus,
    ErrorKind,
    McpServerConfig,
    RouteTarget,
    RunPhase,
    TaskBudget,
    TaskKind,
    TaskRecord,
    TaskStatus,
    WorkerOutput,
)
from drostpp.routing import ModelRouter


def _dummy_ctx(tmp_path: Path, route: RouteTarget, *, mcp_servers=None, max_tokens=50_000) -> AttemptContext:
    now = "2026-11-20T00:00:00Z"
    task = TaskRecord(
        task_id="tsk_1",
        run_id="run_1",
        title="Test",
        kind=TaskKind.WORK,
        prompt="Inspect input",
        role="worker",
        tier=route.tier,
        status=TaskStatus.RUNNING,
        priority=0,
        generation=1,
        active_attempt_id="att_1",
        max_retries=1,
        retry_count=0,
        last_error_sig=None,
        consecutive_same_error=0,
        budget_json="{}",
        metadata_json="{}",
        result_json=None,
        created_at=now,
        updated_at=now,
    )
    att = AttemptRecord(
        attempt_id="att_1",
        run_id="run_1",
        task_id="tsk_1",
        generation=1,
        worker_id="w0",
        provider=route.provider,
        model=route.model,
        status=AttemptStatus.RUNNING,
        pid=None,
        pgid=None,
        container_id=None,
        lease_expires_at=now,
        input_tokens=0,
        output_tokens=0,
        total_tokens=0,
        disk_bytes=0,
        error_kind=None,
        error_message=None,
        started_at=now,
        finished_at=None,
    )
    return AttemptContext(
        run_id="run_1",
        task=task,
        attempt=att,
        prompt="Prompt body",
        attempt_dir=tmp_path / "attempt",
        workspace_dir=tmp_path,
        budget=TaskBudget(max_tokens=max_tokens, max_wall_seconds=10.0),
        route=route,
        mcp_servers=mcp_servers or [],
    )


def test_toml_literal_and_codex_adapter_invocation(tmp_path: Path, monkeypatch) -> None:
    assert toml_literal(["a", 'b"c']) == '["a", "b\\"c"]'
    assert toml_literal({"DROST_MCP_MODE": "compact", "FLAG": True}) == '{DROST_MCP_MODE = "compact", FLAG = true}'

    fake_codex = tmp_path / "fake_codex.py"
    recorded_path = tmp_path / "codex_recorded.json"
    fake_codex.write_text(
        f"""#!{sys.executable}
import json, sys
argv = sys.argv[1:]
prompt = sys.stdin.read()
out_path = argv[argv.index("-o") + 1]
with open({str(recorded_path)!r}, "w") as fp:
    json.dump({{"argv": argv, "prompt": prompt}}, fp)
payload = {{
    "status": "completed",
    "summary": "Codex mock completed",
    "facts": [{{"title": "Codex fact", "body": "Verified OAuth run", "tags": ["codex"], "confidence": 0.9}}],
    "hypotheses": [],
    "findings": [],
    "notes": [],
    "follow_up_tasks": [],
    "blocker_reason": None
}}
with open(out_path, "w") as fp:
    json.dump(payload, fp)
print(json.dumps({{"type": "turn.completed", "usage": {{"input_tokens": 11, "output_tokens": 22}}}}))
""",
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)

    codex_home = tmp_path / "codex_home"
    codex_home.mkdir()
    (codex_home / "auth.json").write_text('{"token":"oauth"}', encoding="utf-8")

    cfg = CodexProviderConfig(binary=str(fake_codex), codex_home=str(codex_home))
    adapter = CodexAdapter(cfg)
    drost_mcp = McpServerConfig(
        name="drost",
        command="docker",
        args=["exec", "-i", "-e", "DROST_MCP_MODE=compact", "drost-ai", "drost-mcp"],
    )
    ctx = _dummy_ctx(tmp_path, RouteTarget(provider="codex", model="gpt-6.2-sol"), mcp_servers=[drost_mcp])
    res = adapter.execute(ctx)
    assert res.success is True
    assert res.total_tokens == 33
    assert res.output is not None and res.output.facts[0]["title"] == "Codex fact"

    recorded = json.loads(recorded_path.read_text(encoding="utf-8"))
    argv = recorded["argv"]
    assert argv[:4] == ["exec", "--ephemeral", "--skip-git-repo-check", "--json"]
    assert "-m" in argv and argv[argv.index("-m") + 1] == "gpt-6.2-sol"
    assert any('mcp_servers.drost.command="docker"' == a for a in argv)
    assert any("mcp_servers.drost.args=" in a for a in argv)
    assert recorded["prompt"] == "Prompt body"


def test_kimi_api_adapter_with_mcp_tools_429_retry_and_no_secret_leak(
    tmp_path: Path, state_dir: Path, monkeypatch
) -> None:
    secret_val = "sk-kimi-super-secret-test-value"
    monkeypatch.setenv("KIMI_API_KEY", secret_val)

    # Create a tiny stdio MCP server script.
    mcp_script = tmp_path / "fake_mcp.py"
    mcp_script.write_text(
        f"""#!{sys.executable}
import json, sys
for line in sys.stdin:
    req = json.loads(line)
    mid = req.get("id")
    method = req.get("method")
    if method == "initialize":
        resp = {{"jsonrpc": "2.0", "id": mid, "result": {{"protocolVersion": "2024-11-05"}}}}
    elif method == "tools/list":
        resp = {{"jsonrpc": "2.0", "id": mid, "result": {{"tools": [{{"name": "echo_info", "description": "Echo tool", "inputSchema": {{"type": "object", "properties": {{"msg": {{"type": "string"}}}}}}}}]}}}}
    elif method == "tools/call":
        args = req["params"]["arguments"]
        resp = {{"jsonrpc": "2.0", "id": mid, "result": {{"content": [{{"type": "text", "text": "MCP_ECHO:" + args.get("msg", "")}}]}}}}
    else:
        continue
    sys.stdout.write(json.dumps(resp) + "\\n")
    sys.stdout.flush()
""",
        encoding="utf-8",
    )
    mcp_script.chmod(0o755)

    seen_auth_headers: list[str] = []
    call_counter = {"n": 0}
    seen_tool_messages: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            seen_auth_headers.append(self.headers.get("Authorization", ""))
            call_counter["n"] += 1
            n = call_counter["n"]
            if n == 1:
                self.send_response(429)
                self.end_headers()
                self.wfile.write(b'{"error":"rate limited"}')
                return
            if n == 2:
                # Request an MCP tool call!
                resp = {
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": "",
                                "tool_calls": [
                                    {
                                        "id": "tc_1",
                                        "type": "function",
                                        "function": {
                                            "name": "drost__echo_info",
                                            "arguments": json.dumps({"msg": "hello-drost"}),
                                        },
                                    }
                                ],
                            }
                        }
                    ],
                }
            else:
                for m in body.get("messages", []):
                    if m.get("role") == "tool":
                        seen_tool_messages.append(m.get("content", ""))
                resp = {
                    "usage": {"prompt_tokens": 20, "completion_tokens": 15, "total_tokens": 35},
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": json.dumps(
                                    {
                                        "status": "completed",
                                        "summary": "Kimi finished with MCP result",
                                        "facts": [
                                            {
                                                "title": "MCP Bridge Worked",
                                                "body": "Saw " + (seen_tool_messages[-1] if seen_tool_messages else ""),
                                                "tags": ["kimi", "mcp"],
                                                "confidence": 0.95,
                                            }
                                        ],
                                        "hypotheses": [],
                                        "findings": [],
                                        "notes": [],
                                        "follow_up_tasks": [],
                                        "blocker_reason": None,
                                    }
                                ),
                            }
                        }
                    ],
                }
            raw = json.dumps(resp).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    srv_thread = threading.Thread(target=server.serve_forever, daemon=True)
    srv_thread.start()

    try:
        cfg = OrchestratorConfig()
        cfg.run.enable_verify_phase = False
        cfg.kimi = KimiProviderConfig(
            mode="api",
            base_url=f"http://127.0.0.1:{port}/v1",
            api_key_env="KIMI_API_KEY",
            default_model="kimi-k2-turbo-preview",
        )
        cfg.routing = RoutingConfig(
            tiers={
                "default": [RouteTarget(provider="kimi", model="kimi-k2-turbo-preview", tier="default")],
                "strong": [RouteTarget(provider="kimi", model="kimi-k2-turbo-preview", tier="strong")],
            }
        )
        cfg.mcp_servers["drost"] = McpServerConfig(
            name="drost", command=sys.executable, args=[str(mcp_script)]
        )

        coord = Coordinator(state_dir, cfg)
        try:
            run = coord.create_run("kimi mcp test")
            coord.store.transition_run_phase(run.run_id, RunPhase.PLANNING)
            coord.store.mark_plan_materialized(run.run_id)
            coord.store.transition_run_phase(run.run_id, RunPhase.RUNNING)
            coord.store.add_task(run.run_id, "Kimi task", "Call drost echo_info")
            with coord.acquire_lock():
                res = coord._drive_run(run.run_id)
            assert res.phase == RunPhase.COMPLETED
            assert res.tokens_used == 50
            assert seen_tool_messages == ["MCP_ECHO:hello-drost"]
            assert all(h == f"Bearer {secret_val}" for h in seen_auth_headers)

            # Verify secret is NEVER stored anywhere in SQLite DB bytes!
            db_bytes = (state_dir / "drostpp.db").read_bytes()
            assert secret_val.encode("utf-8") not in db_bytes
        finally:
            coord.close()
    finally:
        server.shutdown()
        server.server_close()


def test_kimi_cli_adapter_and_router_failover(tmp_path: Path, state_dir: Path) -> None:
    fake_kimi = tmp_path / "fake_kimi.py"
    fake_kimi.write_text(
        f"""#!{sys.executable}
import json, sys
argv = sys.argv[1:]
assert "-p" in argv and "--output-format" in argv and "stream-json" in argv and "--auto" in argv
print(json.dumps({{"role": "assistant", "content": json.dumps({{"status": "completed", "summary": "Kimi CLI ok", "facts": [], "hypotheses": [], "findings": [], "notes": [], "follow_up_tasks": [], "blocker_reason": None}}), "usage": {{"input_tokens": 5, "output_tokens": 7}}}}))
""",
        encoding="utf-8",
    )
    fake_kimi.chmod(0o755)
    kimi_adapter = KimiCliAdapter(KimiProviderConfig(mode="cli", cli_binary=str(fake_kimi)))
    ctx = _dummy_ctx(tmp_path, RouteTarget(provider="kimi", model="kimi-k2"))
    res = kimi_adapter.execute(ctx)
    assert res.success is True
    assert res.total_tokens == 12
    assert res.output is not None and res.output.summary == "Kimi CLI ok"

    # Test ModelRouter cooldown & Codex -> Kimi failover inside Coordinator.
    cfg = OrchestratorConfig()
    cfg.run.enable_verify_phase = False
    cfg.routing = RoutingConfig(
        tiers={
            "default": [
                RouteTarget(provider="codex", model="m-codex", tier="default"),
                RouteTarget(provider="kimi", model="m-kimi", tier="default"),
            ]
        },
        cooldown_seconds=60.0,
    )

    codex_calls = {"n": 0}

    def codex_quota(_ctx):
        codex_calls["n"] += 1
        return AttemptResult(success=False, error_kind=ErrorKind.QUOTA, error_message="HTTP 429 quota")

    def kimi_ok(_ctx):
        return AttemptResult(
            success=True,
            output=WorkerOutput(status="completed", summary="Kimi failover succeeded"),
            total_tokens=20,
        )

    coord = Coordinator(
        state_dir,
        cfg,
        adapters={"codex": MockAdapter(codex_quota), "kimi": MockAdapter(kimi_ok)},
    )
    try:
        run = coord.create_run("failover test")
        coord.store.transition_run_phase(run.run_id, RunPhase.PLANNING)
        coord.store.mark_plan_materialized(run.run_id)
        coord.store.transition_run_phase(run.run_id, RunPhase.RUNNING)
        coord.store.add_task(run.run_id, "Task 1", "one")
        coord.store.add_task(run.run_id, "Task 2", "two")
        with coord.acquire_lock():
            done = coord._drive_run(run.run_id)
        assert done.phase == RunPhase.COMPLETED
        # Task 1 failed over from codex->kimi; Task 2 went straight to kimi because codex is cooling down!
        assert codex_calls["n"] == 1
    finally:
        coord.close()
