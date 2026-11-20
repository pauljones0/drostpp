"""Tests for phase invariants, ARTEX-style crash-recovery regressions, and SIGKILL recovery."""

from __future__ import annotations

import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest

from drostpp.adapters.mock import MockAdapter
from drostpp.config import OrchestratorConfig
from drostpp.coordinator import Coordinator
from drostpp.models import (
    AttemptResult,
    AttemptStatus,
    ErrorKind,
    IllegalTransitionError,
    RunPhase,
    TaskKind,
    TaskStatus,
    WorkerOutput,
)
from drostpp.supervision import pgid_exists, terminate_process_group


def test_unfinished_bootstrap_never_marks_done_on_restart(state_dir: Path) -> None:
    """Regression for ARTEX Finding #1: PLANNING with plan_materialized=0 must not complete on restart."""
    cfg = OrchestratorConfig()
    coord = Coordinator(state_dir, cfg, use_mock=True)
    try:
        run = coord.create_run("bootstrap crash regression")
        coord.store.transition_run_phase(run.run_id, RunPhase.PLANNING)
        # Simulate crash before plan_materialized=1 and before any work tasks exist.
        assert not coord.store.get_run(run.run_id).plan_materialized

        with pytest.raises(IllegalTransitionError):
            coord.store.transition_run_phase(run.run_id, RunPhase.COMPLETED)

        coord.recover(run.run_id)
        recovered = coord.store.get_run(run.run_id)
        assert recovered is not None
        assert recovered.phase == RunPhase.PLANNING
        assert not recovered.plan_materialized
    finally:
        coord.close()

    # Resuming actually runs the planner and completes properly.
    coord2 = Coordinator(state_dir, cfg, use_mock=True)
    try:
        final = coord2.resume(run.run_id)
        assert final.phase == RunPhase.COMPLETED
        assert final.plan_materialized is True
    finally:
        coord2.close()


def test_paused_task_prevents_premature_completion(state_dir: Path) -> None:
    """Regression for ARTEX Finding #2: paused task blocks run completion until resumed."""
    cfg = OrchestratorConfig()
    cfg.run.enable_verify_phase = False
    coord = Coordinator(state_dir, cfg, use_mock=True)
    try:
        run = coord.create_run("paused task test")
        coord.store.transition_run_phase(run.run_id, RunPhase.PLANNING)
        coord.store.mark_plan_materialized(run.run_id)
        coord.store.transition_run_phase(run.run_id, RunPhase.RUNNING)
        t1 = coord.store.add_task(run.run_id, "Task 1", "do 1")
        t2 = coord.store.add_task(run.run_id, "Task 2", "do 2")
        coord.store.pause_task(t2.task_id)

        with coord.acquire_lock():
            after_pause_drive = coord._drive_run(run.run_id)

        assert after_pause_drive.phase == RunPhase.PAUSED
        assert coord.store.get_task(t1.task_id).status == TaskStatus.COMPLETED
        assert coord.store.get_task(t2.task_id).status == TaskStatus.PAUSED

        # Resume task 2, then resume run -> now completes cleanly.
        coord.store.resume_task(t2.task_id)
        final = coord.resume(run.run_id)
        assert final.phase == RunPhase.COMPLETED
        assert coord.store.get_task(t2.task_id).status == TaskStatus.COMPLETED
    finally:
        coord.close()


def test_graceful_shutdown_interrupts_attempt_and_resumes_cleanly(state_dir: Path) -> None:
    cfg = OrchestratorConfig()
    cfg.run.enable_verify_phase = False
    cfg.run.max_workers = 1

    coord_holder: list[Coordinator] = []
    call_count = 0

    def handler(ctx):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Trigger coordinator shutdown mid-task.
            coord_holder[0].request_shutdown()
            ctx.cancel_event.wait(timeout=2.0)
            return AttemptResult(
                success=False,
                error_kind=ErrorKind.HARD_ERROR,
                error_message="cancelled",
                cancelled=True,
            )
        return AttemptResult(
            success=True,
            output=WorkerOutput(status="completed", summary="resumed and finished"),
            total_tokens=10,
        )

    coord = Coordinator(
        state_dir,
        cfg,
        adapters={"codex": MockAdapter(handler), "kimi": MockAdapter(handler), "mock": MockAdapter(handler)},
    )
    coord_holder.append(coord)
    try:
        run = coord.create_run("shutdown resume test")
        coord.store.transition_run_phase(run.run_id, RunPhase.PLANNING)
        coord.store.mark_plan_materialized(run.run_id)
        coord.store.transition_run_phase(run.run_id, RunPhase.RUNNING)
        task = coord.store.add_task(run.run_id, "Interruptible", "work", max_retries=0)

        with coord.acquire_lock():
            paused_run = coord._drive_run(run.run_id)

        assert paused_run.phase == RunPhase.PAUSED
        assert coord.store.get_task(task.task_id).status == TaskStatus.READY
        atts = coord.store.list_attempts(run.run_id, task.task_id)
        assert len(atts) == 1
        assert atts[0].status == AttemptStatus.INTERRUPTED

        # Resume must succeed without consuming max_retries=0.
        finished = coord.resume(run.run_id)
        assert finished.phase == RunPhase.COMPLETED
        assert coord.store.get_task(task.task_id).status == TaskStatus.COMPLETED
    finally:
        coord.close()


def test_recover_kills_orphaned_process_group_after_sigkill(state_dir: Path) -> None:
    """Spawn a real background process group simulating a worker surviving coordinator SIGKILL."""
    cfg = OrchestratorConfig()
    coord = Coordinator(state_dir, cfg, use_mock=True)
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    pgid = os.getpgid(proc.pid)
    try:
        run = coord.create_run("orphan process group recovery")
        coord.store.transition_run_phase(run.run_id, RunPhase.PLANNING)
        coord.store.mark_plan_materialized(run.run_id)
        coord.store.transition_run_phase(run.run_id, RunPhase.RUNNING)
        task = coord.store.add_task(run.run_id, "Crashed work", "work")
        claimed = coord.store.claim_next_task(run.run_id, "w", "mock", "m")
        assert claimed is not None
        _, att = claimed
        coord.store.attach_attempt_runtime(
            task.task_id, att.attempt_id, att.generation, pid=proc.pid, pgid=pgid
        )
        assert pgid_exists(pgid)

        stale = coord.recover(run.run_id)
        assert len(stale) == 1
        proc.wait(timeout=3.0)
        assert not pgid_exists(pgid)
        assert coord.store.get_attempt(att.attempt_id).status == AttemptStatus.INTERRUPTED
        assert coord.store.get_task(task.task_id).status == TaskStatus.READY
    finally:
        if pgid_exists(pgid):
            terminate_process_group(pgid, proc=proc, grace_seconds=0.2)
        coord.close()
