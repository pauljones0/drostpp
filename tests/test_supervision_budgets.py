"""Tests for process-group supervision, grandchild reaping, output/disk/token budgets, and stall detection."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import time

from drostpp.adapters.mock import MockAdapter
from drostpp.config import OrchestratorConfig
from drostpp.coordinator import Coordinator
from drostpp.models import AttemptResult, ErrorKind, RunPhase, TaskStatus
from drostpp.supervision import ProcessSupervisor, pgid_exists


def test_grandchild_inheriting_pipe_is_reaped_when_leader_exits(tmp_path: Path) -> None:
    """Regression for Drost Finding #1: leader exits early leaving grandchild holding stdout/stderr."""
    marker = tmp_path / "grandchild.pgid"
    child_script = tmp_path / "spawn_grandchild.py"
    child_script.write_text(
        f"""
import os, subprocess, sys, time
p = subprocess.Popen(
    [sys.executable, "-c", "import os, time; open({str(marker)!r}, 'w').write(str(os.getpgid(0))); time.sleep(30)"],
    stdin=subprocess.DEVNULL,
)
# Wait briefly so grandchild writes pgid, then leader exits leaving stdout/stderr open in grandchild!
for _ in range(50):
    if os.path.exists({str(marker)!r}):
        break
    time.sleep(0.02)
os._exit(0)
""",
        encoding="utf-8",
    )

    sup = ProcessSupervisor()
    res = sup.run(
        [sys.executable, str(child_script)],
        wall_timeout=5.0,
    )
    assert res.returncode == 0
    assert marker.exists()
    pgid = int(marker.read_text(encoding="utf-8").strip())
    assert pgid == res.pgid
    # Entire process group must be dead at return!
    assert not pgid_exists(pgid)


def test_sigterm_ignoring_process_escalates_to_sigkill_on_timeout(tmp_path: Path) -> None:
    stubborn = tmp_path / "stubborn.py"
    stubborn.write_text(
        "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(30)",
        encoding="utf-8",
    )
    sup = ProcessSupervisor()
    res = sup.run(
        [sys.executable, str(stubborn)],
        wall_timeout=0.3,
        grace_seconds=0.25,
    )
    assert res.timed_out is True
    assert not pgid_exists(res.pgid)
    assert res.duration_seconds < 3.0


def test_output_cap_and_disk_watchdog(tmp_path: Path) -> None:
    sup = ProcessSupervisor()
    # Multi-MB stdout flood must be capped cleanly without OOM.
    res = sup.run(
        [sys.executable, "-c", "print('A' * 300_000, flush=True)"],
        wall_timeout=5.0,
        max_output_bytes=8192,
    )
    assert res.returncode == 0
    assert res.stdout_truncated is True
    assert len(res.stdout.encode("utf-8")) <= 8192

    # Runaway disk write inside watch dir triggers kill_reason.
    disk_dir = tmp_path / "attempt_disk"
    disk_dir.mkdir()
    res_disk = sup.run(
        [
            sys.executable,
            "-c",
            f"open({str(disk_dir / 'blob.bin')!r}, 'wb').write(b'x' * 200_000); import time; time.sleep(10)",
        ],
        wall_timeout=5.0,
        max_disk_bytes=32_768,
        disk_watch_dir=disk_dir,
        grace_seconds=0.1,
    )
    assert res_disk.kill_reason is not None and "disk limit exceeded" in res_disk.kill_reason
    assert not pgid_exists(res_disk.pgid)


def test_stall_detector_and_run_token_budget_halt_run(state_dir: Path) -> None:
    cfg = OrchestratorConfig()
    cfg.run.enable_verify_phase = False
    cfg.budgets.max_same_error_repeats = 2

    def always_same_fail(_ctx):
        return AttemptResult(
            success=False,
            error_kind=ErrorKind.HARD_ERROR,
            error_message="Assertion failed on line 42 at id=abcdef1234",
            total_tokens=10,
        )

    coord = Coordinator(
        state_dir,
        cfg,
        adapters={"codex": MockAdapter(always_same_fail), "kimi": MockAdapter(always_same_fail)},
    )
    try:
        run = coord.create_run("stall test")
        coord.store.transition_run_phase(run.run_id, RunPhase.PLANNING)
        coord.store.mark_plan_materialized(run.run_id)
        coord.store.transition_run_phase(run.run_id, RunPhase.RUNNING)
        # Allow 5 retries, but max_same_error_repeats=2 must halt after attempt #2!
        t = coord.store.add_task(run.run_id, "Stalling task", "fail repeatedly", max_retries=5)

        with coord.acquire_lock():
            final = coord._drive_run(run.run_id)
        assert final.phase == RunPhase.COMPLETED  # all tasks settled (task FAILED)
        refreshed = coord.store.get_task(t.task_id)
        assert refreshed.status == TaskStatus.FAILED
        assert len(coord.store.list_attempts(run.run_id, t.task_id)) == 2
    finally:
        coord.close()

    # Now verify run-level token budget stops run admission cleanly.
    state2 = state_dir.parent / "state_budget"
    cfg2 = OrchestratorConfig()
    cfg2.run.enable_verify_phase = False
    cfg2.run.max_workers = 1
    cfg2.budgets.max_run_tokens = 100

    def expensive_worker(ctx):
        return AttemptResult(
            success=True,
            total_tokens=150,
            output=__import__("drostpp.models", fromlist=["WorkerOutput"]).WorkerOutput(
                status="completed", summary="expensive"
            ),
        )

    coord2 = Coordinator(
        state2,
        cfg2,
        adapters={"codex": MockAdapter(expensive_worker), "kimi": MockAdapter(expensive_worker)},
    )
    try:
        run2 = coord2.create_run("budget stop test")
        coord2.store.transition_run_phase(run2.run_id, RunPhase.PLANNING)
        coord2.store.mark_plan_materialized(run2.run_id)
        coord2.store.transition_run_phase(run2.run_id, RunPhase.RUNNING)
        coord2.store.add_task(run2.run_id, "T1", "1")
        coord2.store.add_task(run2.run_id, "T2", "2")
        with coord2.acquire_lock():
            res2 = coord2._drive_run(run2.run_id)
        assert res2.phase == RunPhase.FAILED
        assert res2.error_message and "token budget exhausted" in res2.error_message
    finally:
        coord2.close()
