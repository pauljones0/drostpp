"""Tests for Drost MCP wiring, health predicate, defensive workspace listing, artifact sync, and atomic JSON."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys

import pytest

from drostpp.blackboard import Blackboard
from drostpp.config import DrostConfig
from drostpp.integrations.drost import (
    DrostWorkspaceBridge,
    atomic_write_json,
    build_drost_mcp_config,
    check_drost_health,
)
from drostpp.integrations.mcp import McpStdioClient
from drostpp.models import BudgetExceededError
from drostpp.store import SQLiteStore
from drostpp.supervision import pgid_exists


def test_build_drost_mcp_config_modes() -> None:
    cfg_compact = DrostConfig(enabled=True, container_name="my-drost", mcp_mode="compact")
    srv = build_drost_mcp_config(cfg_compact)
    assert srv.command == "docker"
    assert srv.args == ["exec", "-i", "-e", "DROST_MCP_MODE=compact", "my-drost", "drost-mcp"]

    cfg_full = DrostConfig(
        enabled=True,
        container_name="my-drost",
        mcp_mode="full",
        tool_categories=["web", "utilities"],
    )
    srv2 = build_drost_mcp_config(cfg_full)
    assert "DROST_MCP_MODE=full" in srv2.args
    assert "DROST_TOOL_CATEGORIES=web,utilities" in srv2.args


def test_mcp_stdio_client_against_fake_drost_mcp_server(tmp_path: Path) -> None:
    fake_server = tmp_path / "fake_drost_mcp.py"
    fake_server.write_text(
        f"""#!{sys.executable}
import json, sys
for line in sys.stdin:
    req = json.loads(line)
    mid = req.get("id")
    method = req.get("method")
    if method == "initialize":
        res = {{"protocolVersion": "2024-11-05", "serverInfo": {{"name": "Drost AI"}}}}
    elif method == "tools/list":
        res = {{"tools": [{{"name": "drost_catalog", "description": "Catalog", "inputSchema": {{"type": "object", "properties": {{}}}}}}]}}
    elif method == "tools/call":
        res = {{"structuredContent": {{"payload": "Z" * 10_000}}}}
    else:
        continue
    sys.stdout.write(json.dumps({{"jsonrpc": "2.0", "id": mid, "result": res}}) + "\\n")
    sys.stdout.flush()
""",
        encoding="utf-8",
    )

    from drostpp.models import McpServerConfig

    srv = McpServerConfig(
        name="drost",
        command=sys.executable,
        args=[str(fake_server)],
        max_result_bytes=1024,
    )
    client = McpStdioClient(srv, spill_dir=tmp_path / "spill")
    client.start()
    pgid = client._pgid
    try:
        tools = client.list_tools()
        assert [t["name"] for t in tools] == ["drost_catalog"]
        out = client.call_tool("drost_catalog", {})
        assert "truncated" in out
        assert len(out.encode("utf-8")) < 2048
    finally:
        client.close()
    assert not pgid_exists(pgid)


def test_check_drost_health_rejects_nonzero_exit_even_if_json_says_healthy(tmp_path: Path) -> None:
    """Regression for Drost Finding #8: self-test JSON can report healthy while exit code is 1."""
    fake_docker = tmp_path / "fake_docker"
    fake_docker.write_text(
        f"""#!{sys.executable}
import json, sys
print(json.dumps({{"status": "healthy", "missing_executables": []}}))
sys.exit(1)
""",
        encoding="utf-8",
    )
    fake_docker.chmod(0o755)
    res = check_drost_health(DrostConfig(enabled=True, docker_binary=str(fake_docker)))
    assert res["healthy"] is False
    assert res["exit_code"] == 1


def test_drost_workspace_bridge_resilience_sync_and_atomic_write(tmp_path: Path) -> None:
    ws = tmp_path / "drost_ws"
    engs = ws / "engagements"
    valid_id = "eng_20261120_0123456789abcdef0123456789abcdef"
    bad_json_id = "eng_20261120_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    missing_ts_id = "eng_20261120_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

    # Valid engagement with evidence, duplicate content, and a dangling/escaping symlink.
    v_dir = engs / valid_id
    for sub in ("artifacts", "evidence", "findings"):
        (v_dir / sub).mkdir(parents=True)
    atomic_write_json(
        v_dir / "engagement.json",
        {
            "schema_version": 1,
            "engagement_id": valid_id,
            "name": "Example Case",
            "targets": ["example.local"],
            "created_at": "2026-11-20T00:00:00Z",
        },
    )
    (v_dir / "evidence" / "trace.txt").write_text("evidence payload", encoding="utf-8")
    (v_dir / "artifacts" / "dup_trace.txt").write_text("evidence payload", encoding="utf-8")
    (v_dir / "findings" / "note.md").write_text("# Finding\nConfirmed trace.", encoding="utf-8")
    os.symlink("/etc/passwd", v_dir / "evidence" / "escape_link")
    os.symlink(str(tmp_path / "nonexistent"), v_dir / "evidence" / "dangling_link")

    # Corrupt sibling and missing-timestamp sibling (Drost Finding #6 regression!).
    (engs / bad_json_id).mkdir(parents=True)
    (engs / bad_json_id / "engagement.json").write_text("{corrupt", encoding="utf-8")
    (engs / missing_ts_id).mkdir(parents=True)
    (engs / missing_ts_id / "engagement.json").write_text(
        json.dumps({"engagement_id": missing_ts_id, "targets": ["x"]}),
        encoding="utf-8",
    )

    bridge = DrostWorkspaceBridge(ws)
    listing = bridge.list_engagements()
    assert [e["engagement_id"] for e in listing["engagements"]] == [valid_id]
    assert len(listing["invalid_engagements"]) == 2

    store = SQLiteStore(tmp_path / "drostpp.db")
    bb = Blackboard(store)
    try:
        run = store.create_run("sync test", drost_engagement_id=valid_id)
        sync_res = bridge.sync_engagement_to_run(
            store,
            bb,
            run_id=run.run_id,
            engagement_id=valid_id,
            artifact_store_dir=tmp_path / "store_arts",
            max_import_bytes=1024 * 1024,
        )
        assert sync_res["imported_count"] == 2
        assert sync_res["skipped_duplicates"] == 1
        assert sync_res["skipped_symlinks"] == 2
        assert len(bb.list_entries(run.run_id)) == 2

        # Enforce import byte limit cleanly.
        run2 = store.create_run("tiny quota", drost_engagement_id=valid_id)
        with pytest.raises(BudgetExceededError):
            bridge.sync_engagement_to_run(
                store,
                bb,
                run_id=run2.run_id,
                engagement_id=valid_id,
                artifact_store_dir=tmp_path / "store_arts2",
                max_import_bytes=5,
            )
    finally:
        store.close()

    # Concurrent atomic_write_json never leaves partial/ENOENT failures (Drost Finding #3).
    target_json = tmp_path / "concurrent.json"
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda i: atomic_write_json(target_json, {"writer": i}), range(40)))
    loaded = json.loads(target_json.read_text(encoding="utf-8"))
    assert "writer" in loaded
