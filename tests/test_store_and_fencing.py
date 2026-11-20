"""Tests for SQLite WAL durability, single-writer lock, atomic journaling, DAG deps, and generation fencing."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import sys

import pytest

from drostpp.models import (
    AttemptStatus,
    BlackboardKind,
    CoordinatorLockError,
    FencedAttemptError,
    IllegalTransitionError,
    RunPhase,
    TaskKind,
    TaskStatus,
)
from drostpp.store import CoordinatorLock, SQLiteStore


def test_wal_enabled_and_exclusive_coordinator_lock(tmp_path: Path) -> None:
    db_path = tmp_path / "drostpp.db"
    store = SQLiteStore(db_path)
    try:
        mode = store._conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode.lower() == "wal"
    finally:
        store.close()

    lock_path = tmp_path / "coordinator.lock"
    with CoordinatorLock(lock_path, db_path):
        with pytest.raises(CoordinatorLockError):
            with CoordinatorLock(lock_path, db_path):
                pass

        # A second OS process must also be rejected immediately.
        code = (
            "import sys\n"
            "sys.path.insert(0, %r)\n"
            "from pathlib import Path\n"
            "from drostpp.store import CoordinatorLock\n"
            "from drostpp.models import CoordinatorLockError\n"
            "try:\n"
            "  with CoordinatorLock(Path(%r)):\n"
            "    sys.exit(2)\n"
            "except CoordinatorLockError:\n"
            "  sys.exit(0)\n"
        ) % (str(Path(__file__).resolve().parent.parent / "src"), str(lock_path))
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr

    # After release, lock can be acquired again.
    with CoordinatorLock(lock_path, db_path):
        assert lock_path.exists()


def test_atomic_rollback_leaves_zero_orphan_events(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "drostpp.db")
    try:
        run = store.create_run("atomic check")
        before_events = len(store.list_events(run.run_id))

        with pytest.raises(RuntimeError, match="injected"):
            with store._txn() as conn:
                store._append_event(conn, run.run_id, "should.rollback", "test", {"x": 1})
                conn.execute(
                    "UPDATE runs SET goal = 'mutated' WHERE run_id = ?",
                    (run.run_id,),
                )
                raise RuntimeError("injected")

        after_events = len(store.list_events(run.run_id))
        assert after_events == before_events
        refreshed = store.get_run(run.run_id)
        assert refreshed is not None
        assert refreshed.goal == "atomic check"
    finally:
        store.close()


def test_concurrent_claim_contention_single_winner(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "drostpp.db")
    try:
        run = store.create_run("contention")
        store.transition_run_phase(run.run_id, RunPhase.PLANNING)
        store.mark_plan_materialized(run.run_id)
        store.transition_run_phase(run.run_id, RunPhase.RUNNING)
        task = store.add_task(run.run_id, "Single ready task", "do work")

        def try_claim(idx: int):
            return store.claim_next_task(
                run.run_id, f"worker-{idx}", "mock", "m1", lease_seconds=60
            )

        with ThreadPoolExecutor(max_workers=16) as pool:
            results = list(pool.map(try_claim, range(16)))

        winners = [r for r in results if r is not None]
        assert len(winners) == 1
        claimed_task, claimed_att = winners[0]
        assert claimed_task.task_id == task.task_id
        assert claimed_task.generation == 1
        assert claimed_att.generation == 1
    finally:
        store.close()


def test_lease_reclaim_fences_stale_generation_writes(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "drostpp.db")
    try:
        run = store.create_run("fencing")
        store.transition_run_phase(run.run_id, RunPhase.PLANNING)
        store.mark_plan_materialized(run.run_id)
        store.transition_run_phase(run.run_id, RunPhase.RUNNING)
        task = store.add_task(run.run_id, "Fenced task", "do work", max_retries=2)

        claim1 = store.claim_next_task(run.run_id, "worker-1", "mock", "m1", lease_seconds=10)
        assert claim1 is not None
        t1, att1 = claim1
        assert att1.generation == 1

        # Reclaim after lease expiry.
        future_iso = (datetime.now(timezone.utc) + timedelta(seconds=60)).isoformat().replace(
            "+00:00", "Z"
        )
        expired = store.reclaim_expired_leases(run.run_id, now_iso=future_iso)
        assert len(expired) == 1
        assert expired[0].attempt_id == att1.attempt_id

        # Second worker claims generation 2.
        claim2 = store.claim_next_task(run.run_id, "worker-2", "mock", "m1", lease_seconds=60)
        assert claim2 is not None
        t2, att2 = claim2
        assert t2.generation == 2
        assert att2.generation == 2

        # All late writes from generation 1 must fail with FencedAttemptError.
        with pytest.raises(FencedAttemptError):
            store.heartbeat_attempt(t1.task_id, att1.attempt_id, 1)

        with pytest.raises(FencedAttemptError):
            store.add_blackboard_entry(
                run.run_id,
                BlackboardKind.FINDING,
                "Stale finding",
                "Should never land",
                "fp-stale-1",
                task_id=t1.task_id,
                attempt_id=att1.attempt_id,
                generation=1,
            )

        with pytest.raises(FencedAttemptError):
            store.complete_attempt(
                t1.task_id,
                att1.attempt_id,
                1,
                result={"summary": "stale success"},
                total_tokens=999,
            )

        # Generation 2 remains completely intact and completes cleanly.
        assert store.list_blackboard_entries(run.run_id) == []
        completed = store.complete_attempt(
            t2.task_id,
            att2.attempt_id,
            2,
            result={"summary": "fresh success"},
            total_tokens=42,
        )
        assert completed.status == TaskStatus.COMPLETED
        assert completed.generation == 2
        assert store.get_attempt(att1.attempt_id).status == AttemptStatus.TIMED_OUT
        assert store.get_attempt(att2.attempt_id).status == AttemptStatus.SUCCEEDED

        fenced_events = [
            e for e in store.list_events(run.run_id) if e["event_type"] == "attempt.fenced_rejected"
        ]
        assert len(fenced_events) == 3
    finally:
        store.close()


def test_dependency_dag_promotion_blocking_and_cycle_rejection(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "drostpp.db")
    try:
        run = store.create_run("dag test")
        store.transition_run_phase(run.run_id, RunPhase.PLANNING)
        store.mark_plan_materialized(run.run_id)
        store.transition_run_phase(run.run_id, RunPhase.RUNNING)

        root = store.add_task(run.run_id, "Root", "step 1", max_retries=0)
        child = store.add_task(run.run_id, "Child", "step 2", depends_on=[root.task_id])
        sibling = store.add_task(run.run_id, "Will fail", "bad", max_retries=0)
        blocked_child = store.add_task(
            run.run_id, "Downstream", "blocked", depends_on=[sibling.task_id]
        )

        # Cycle detection check.
        with pytest.raises(IllegalTransitionError, match="cycle"):
            store.add_dependency(root.task_id, child.task_id)

        assert store.get_task(child.task_id).status == TaskStatus.PENDING

        # Claim and complete Root -> Child becomes READY.
        c1 = store.claim_next_task(run.run_id, "w", "mock", "m")
        assert c1 is not None and c1[0].task_id == root.task_id
        # Child still cannot be claimed while Root is running.
        c_next = store.claim_next_task(run.run_id, "w", "mock", "m")
        assert c_next is not None and c_next[0].task_id == sibling.task_id
        assert store.claim_next_task(run.run_id, "w", "mock", "m") is None

        store.complete_attempt(root.task_id, c1[1].attempt_id, c1[1].generation)
        assert store.get_task(child.task_id).status == TaskStatus.READY

        # Fail sibling -> Downstream becomes BLOCKED.
        from drostpp.models import ErrorKind

        store.fail_attempt(
            sibling.task_id,
            c_next[1].attempt_id,
            c_next[1].generation,
            error_kind=ErrorKind.HARD_ERROR,
            error_message="boom",
        )
        assert store.get_task(blocked_child.task_id).status == TaskStatus.BLOCKED
    finally:
        store.close()
