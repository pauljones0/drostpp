"""SQLite WAL state engine, exclusive coordinator lock, event journal, and generation fencing."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import threading
from typing import Any, Callable, Iterator
import uuid

from .models import (
    ArtifactRecord,
    AttemptRecord,
    AttemptStatus,
    BlackboardEntry,
    BlackboardKind,
    CoordinatorLockError,
    DiversityAssignment,
    ErrorKind,
    FencedAttemptError,
    IllegalTransitionError,
    RunBudget,
    RunPhase,
    RunRecord,
    TaskBudget,
    TaskKind,
    TaskRecord,
    TaskStatus,
)

LEGAL_PHASE_TRANSITIONS: dict[RunPhase, frozenset[RunPhase]] = {
    RunPhase.INIT: frozenset({RunPhase.PLANNING, RunPhase.PAUSED, RunPhase.FAILED, RunPhase.CANCELLED}),
    RunPhase.PLANNING: frozenset({RunPhase.RUNNING, RunPhase.PAUSED, RunPhase.FAILED, RunPhase.CANCELLED}),
    RunPhase.RUNNING: frozenset(
        {RunPhase.VERIFYING, RunPhase.COMPLETED, RunPhase.PAUSED, RunPhase.FAILED, RunPhase.CANCELLED}
    ),
    RunPhase.VERIFYING: frozenset(
        {RunPhase.RUNNING, RunPhase.COMPLETED, RunPhase.PAUSED, RunPhase.FAILED, RunPhase.CANCELLED}
    ),
    RunPhase.PAUSED: frozenset(
        {RunPhase.PLANNING, RunPhase.RUNNING, RunPhase.VERIFYING, RunPhase.FAILED, RunPhase.CANCELLED}
    ),
    RunPhase.COMPLETED: frozenset(),
    RunPhase.FAILED: frozenset(),
    RunPhase.CANCELLED: frozenset(),
}

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_run_seq ON events(run_id, seq);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    goal TEXT NOT NULL,
    phase TEXT NOT NULL,
    plan_materialized INTEGER NOT NULL DEFAULT 0,
    seed INTEGER NOT NULL,
    config_json TEXT NOT NULL,
    budget_json TEXT NOT NULL,
    tokens_used INTEGER NOT NULL DEFAULT 0,
    disk_bytes INTEGER NOT NULL DEFAULT 0,
    drost_engagement_id TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    kind TEXT NOT NULL,
    prompt TEXT NOT NULL,
    role TEXT NOT NULL,
    tier TEXT NOT NULL,
    status TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 0,
    generation INTEGER NOT NULL DEFAULT 0,
    active_attempt_id TEXT,
    max_retries INTEGER NOT NULL DEFAULT 2,
    retry_count INTEGER NOT NULL DEFAULT 0,
    last_error_sig TEXT,
    consecutive_same_error INTEGER NOT NULL DEFAULT 0,
    budget_json TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    result_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_run_claim
    ON tasks(run_id, status, priority DESC, created_at ASC, task_id ASC);

CREATE TABLE IF NOT EXISTS task_deps (
    task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    depends_on_task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    PRIMARY KEY (task_id, depends_on_task_id)
);

CREATE TABLE IF NOT EXISTS attempts (
    attempt_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    generation INTEGER NOT NULL,
    worker_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    status TEXT NOT NULL,
    pid INTEGER,
    pgid INTEGER,
    container_id TEXT,
    lease_expires_at TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    disk_bytes INTEGER NOT NULL DEFAULT 0,
    error_kind TEXT,
    error_message TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    UNIQUE(task_id, generation)
);

CREATE INDEX IF NOT EXISTS idx_attempts_run_status ON attempts(run_id, status, lease_expires_at);

CREATE TABLE IF NOT EXISTS blackboard_entries (
    entry_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    task_id TEXT,
    attempt_id TEXT,
    generation INTEGER,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    tags_json TEXT NOT NULL DEFAULT '[]',
    fingerprint TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.5,
    supersedes_id TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_bb_run_kind ON blackboard_entries(run_id, kind, created_at);
CREATE INDEX IF NOT EXISTS idx_bb_run_fp ON blackboard_entries(run_id, fingerprint);

CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    task_id TEXT,
    attempt_id TEXT,
    sha256 TEXT NOT NULL,
    rel_path TEXT NOT NULL,
    source_path TEXT,
    size_bytes INTEGER NOT NULL,
    media_type TEXT NOT NULL DEFAULT 'application/octet-stream',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_artifacts_run_sha ON artifacts(run_id, sha256);

CREATE TABLE IF NOT EXISTS diversity_assignments (
    run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    task_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    generation INTEGER NOT NULL,
    persona TEXT NOT NULL,
    kb_item_ids_json TEXT NOT NULL DEFAULT '[]',
    angle_seed INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (task_id, generation)
);
"""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_iso(dt: datetime | None = None) -> str:
    target = dt or utc_now()
    return target.isoformat().replace("+00:00", "Z")


def parse_iso(ts: str) -> datetime:
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    return datetime.fromisoformat(ts)


class CoordinatorLock:
    """Exclusive non-blocking OS file lock enforcing a single live coordinator per state dir."""

    def __init__(self, lock_path: Path, db_path: Path | None = None) -> None:
        self.lock_path = Path(lock_path)
        self.db_path = db_path
        self._fd: int | None = None

    def acquire(self) -> None:
        if self._fd is not None:
            return
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(fd)
            raise CoordinatorLockError(
                f"coordinator lock already held at {self.lock_path}"
            ) from exc

        try:
            os.ftruncate(fd, 0)
            os.lseek(fd, 0, os.SEEK_SET)
            payload = json.dumps(
                {
                    "pid": os.getpid(),
                    "acquired_at": utc_iso(),
                    "db_path": str(self.db_path) if self.db_path else None,
                },
                sort_keys=True,
            ).encode("utf-8")
            os.write(fd, payload)
            os.fsync(fd)
        except OSError:
            # Lock ownership is held by flock; metadata write failure shouldn't leak fd.
            pass
        self._fd = fd

    def release(self) -> None:
        fd = self._fd
        if fd is None:
            return
        self._fd = None
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    def __enter__(self) -> CoordinatorLock:
        self.acquire()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.release()


def _row_to_run(row: sqlite3.Row) -> RunRecord:
    return RunRecord(
        run_id=row["run_id"],
        goal=row["goal"],
        phase=RunPhase(row["phase"]),
        plan_materialized=bool(row["plan_materialized"]),
        seed=int(row["seed"]),
        config_json=row["config_json"],
        budget_json=row["budget_json"],
        tokens_used=int(row["tokens_used"]),
        disk_bytes=int(row["disk_bytes"]),
        drost_engagement_id=row["drost_engagement_id"],
        error_message=row["error_message"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        finished_at=row["finished_at"],
    )


def _row_to_task(row: sqlite3.Row) -> TaskRecord:
    return TaskRecord(
        task_id=row["task_id"],
        run_id=row["run_id"],
        title=row["title"],
        kind=TaskKind(row["kind"]),
        prompt=row["prompt"],
        role=row["role"],
        tier=row["tier"],
        status=TaskStatus(row["status"]),
        priority=int(row["priority"]),
        generation=int(row["generation"]),
        active_attempt_id=row["active_attempt_id"],
        max_retries=int(row["max_retries"]),
        retry_count=int(row["retry_count"]),
        last_error_sig=row["last_error_sig"],
        consecutive_same_error=int(row["consecutive_same_error"]),
        budget_json=row["budget_json"],
        metadata_json=row["metadata_json"],
        result_json=row["result_json"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_attempt(row: sqlite3.Row) -> AttemptRecord:
    return AttemptRecord(
        attempt_id=row["attempt_id"],
        run_id=row["run_id"],
        task_id=row["task_id"],
        generation=int(row["generation"]),
        worker_id=row["worker_id"],
        provider=row["provider"],
        model=row["model"],
        status=AttemptStatus(row["status"]),
        pid=row["pid"],
        pgid=row["pgid"],
        container_id=row["container_id"],
        lease_expires_at=row["lease_expires_at"],
        input_tokens=int(row["input_tokens"]),
        output_tokens=int(row["output_tokens"]),
        total_tokens=int(row["total_tokens"]),
        disk_bytes=int(row["disk_bytes"]),
        error_kind=ErrorKind(row["error_kind"]) if row["error_kind"] else None,
        error_message=row["error_message"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
    )


def _row_to_bb(row: sqlite3.Row) -> BlackboardEntry:
    return BlackboardEntry(
        entry_id=row["entry_id"],
        run_id=row["run_id"],
        task_id=row["task_id"],
        attempt_id=row["attempt_id"],
        generation=int(row["generation"]) if row["generation"] is not None else None,
        kind=BlackboardKind(row["kind"]),
        title=row["title"],
        body=row["body"],
        tags=json.loads(row["tags_json"]),
        fingerprint=row["fingerprint"],
        confidence=float(row["confidence"]),
        supersedes_id=row["supersedes_id"],
        created_at=row["created_at"],
    )


def _row_to_artifact(row: sqlite3.Row) -> ArtifactRecord:
    return ArtifactRecord(
        artifact_id=row["artifact_id"],
        run_id=row["run_id"],
        task_id=row["task_id"],
        attempt_id=row["attempt_id"],
        sha256=row["sha256"],
        rel_path=row["rel_path"],
        source_path=row["source_path"],
        size_bytes=int(row["size_bytes"]),
        media_type=row["media_type"],
        metadata=json.loads(row["metadata_json"]),
        created_at=row["created_at"],
    )


class SQLiteStore:
    """Durable SQLite WAL state engine with atomic event+projection transactions."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._in_txn = False
        self._conn = sqlite3.connect(
            self.db_path,
            timeout=5.0,
            isolation_level=None,
            check_same_thread=False,
        )
        self._conn.row_factory = sqlite3.Row
        self._configure_connection()
        self._init_schema()

    def _configure_connection(self) -> None:
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=FULL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA busy_timeout=5000")

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(_SCHEMA_SQL)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    @contextmanager
    def _txn(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            if self._in_txn:
                raise RuntimeError("nested SQLiteStore._txn() is forbidden")
            self._in_txn = True
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield self._conn
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
            else:
                self._conn.execute("COMMIT")
            finally:
                self._in_txn = False

    def _append_event(
        self,
        conn: sqlite3.Connection,
        run_id: str,
        event_type: str,
        actor: str,
        payload: dict[str, Any],
        *,
        ts: str | None = None,
    ) -> int:
        cur = conn.execute(
            """
            INSERT INTO events (run_id, ts, event_type, actor, payload_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (run_id, ts or utc_iso(), event_type, actor, json.dumps(payload, sort_keys=True)),
        )
        return int(cur.lastrowid)

    def _assert_active_fence(
        self,
        conn: sqlite3.Connection,
        task_id: str,
        attempt_id: str,
        generation: int,
        *,
        actor: str = "worker",
    ) -> tuple[sqlite3.Row, sqlite3.Row]:
        task = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        attempt = conn.execute("SELECT * FROM attempts WHERE attempt_id = ?", (attempt_id,)).fetchone()
        valid = (
            task is not None
            and attempt is not None
            and task["status"] == TaskStatus.RUNNING
            and task["active_attempt_id"] == attempt_id
            and int(task["generation"]) == int(generation)
            and attempt["task_id"] == task_id
            and int(attempt["generation"]) == int(generation)
            and attempt["status"] in (AttemptStatus.STARTING, AttemptStatus.RUNNING)
        )
        if valid:
            assert task is not None and attempt is not None
            return task, attempt

        run_id = (
            task["run_id"]
            if task is not None
            else (attempt["run_id"] if attempt is not None else "unknown")
        )
        now = utc_iso()
        if attempt is not None and attempt["status"] in (
            AttemptStatus.STARTING,
            AttemptStatus.RUNNING,
        ):
            conn.execute(
                """
                UPDATE attempts
                SET status = ?, error_kind = ?, error_message = ?, finished_at = ?
                WHERE attempt_id = ? AND status IN ('starting', 'running')
                """,
                (
                    AttemptStatus.FENCED,
                    ErrorKind.FENCED,
                    "stale generation/attempt rejected",
                    now,
                    attempt_id,
                ),
            )
        self._append_event(
            conn,
            run_id,
            "attempt.fenced_rejected",
            actor,
            {
                "task_id": task_id,
                "attempt_id": attempt_id,
                "generation": generation,
                "actual_generation": int(task["generation"]) if task is not None else None,
                "actual_active_attempt_id": task["active_attempt_id"] if task is not None else None,
                "task_status": task["status"] if task is not None else None,
            },
            ts=now,
        )
        # Commit the rejection audit event before raising so evidence survives.
        conn.execute("COMMIT")
        conn.execute("BEGIN IMMEDIATE")
        raise FencedAttemptError(
            f"fenced write rejected for task={task_id} attempt={attempt_id} gen={generation}"
        )

    def _promote_and_block_pending(
        self, conn: sqlite3.Connection, run_id: str, now: str
    ) -> None:
        pending = conn.execute(
            "SELECT task_id FROM tasks WHERE run_id = ? AND status = ?",
            (run_id, TaskStatus.PENDING),
        ).fetchall()
        for row in pending:
            tid = row["task_id"]
            deps = conn.execute(
                """
                SELECT d.depends_on_task_id, t.status
                FROM task_deps d
                JOIN tasks t ON t.task_id = d.depends_on_task_id
                WHERE d.task_id = ?
                """,
                (tid,),
            ).fetchall()
            dep_statuses = [d["status"] for d in deps]
            if any(
                s in (TaskStatus.FAILED, TaskStatus.BLOCKED, TaskStatus.CANCELLED)
                for s in dep_statuses
            ):
                conn.execute(
                    "UPDATE tasks SET status = ?, updated_at = ? WHERE task_id = ? AND status = ?",
                    (TaskStatus.BLOCKED, now, tid, TaskStatus.PENDING),
                )
                self._append_event(
                    conn,
                    run_id,
                    "task.blocked",
                    "coordinator",
                    {"task_id": tid, "reason": "upstream dependency terminal failure"},
                    ts=now,
                )
            elif all(s == TaskStatus.COMPLETED for s in dep_statuses):
                conn.execute(
                    "UPDATE tasks SET status = ?, updated_at = ? WHERE task_id = ? AND status = ?",
                    (TaskStatus.READY, now, tid, TaskStatus.PENDING),
                )
                self._append_event(
                    conn,
                    run_id,
                    "task.ready",
                    "coordinator",
                    {"task_id": tid},
                    ts=now,
                )

    def create_run(
        self,
        goal: str,
        *,
        run_id: str | None = None,
        seed: int | None = None,
        config: dict[str, Any] | None = None,
        budget: RunBudget | None = None,
        drost_engagement_id: str | None = None,
    ) -> RunRecord:
        rid = run_id or f"run_{utc_now().strftime('%Y%m%d')}_{uuid.uuid4().hex[:12]}"
        effective_seed = seed if seed is not None else int.from_bytes(os.urandom(4), "big")
        now = utc_iso()
        budget_obj = budget or RunBudget()
        cfg_json = json.dumps(config or {}, sort_keys=True)
        budget_json = json.dumps(budget_obj.to_dict(), sort_keys=True)

        with self._txn() as conn:
            conn.execute(
                """
                INSERT INTO runs (
                    run_id, goal, phase, plan_materialized, seed,
                    config_json, budget_json, tokens_used, disk_bytes,
                    drost_engagement_id, error_message, created_at, updated_at, finished_at
                )
                VALUES (?, ?, ?, 0, ?, ?, ?, 0, 0, ?, NULL, ?, ?, NULL)
                """,
                (
                    rid,
                    goal,
                    RunPhase.INIT,
                    effective_seed,
                    cfg_json,
                    budget_json,
                    drost_engagement_id,
                    now,
                    now,
                ),
            )
            self._append_event(
                conn,
                rid,
                "run.created",
                "coordinator",
                {
                    "goal": goal,
                    "seed": effective_seed,
                    "drost_engagement_id": drost_engagement_id,
                },
                ts=now,
            )
            row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (rid,)).fetchone()
            assert row is not None
            return _row_to_run(row)

    def get_run(self, run_id: str) -> RunRecord | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
            return _row_to_run(row) if row is not None else None

    def list_runs(self) -> list[RunRecord]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM runs ORDER BY created_at DESC"
            ).fetchall()
            return [_row_to_run(r) for r in rows]

    def mark_plan_materialized(
        self,
        run_id: str,
        *,
        actor: str = "coordinator",
    ) -> RunRecord:
        now = utc_iso()
        with self._txn() as conn:
            row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
            if row is None:
                raise IllegalTransitionError(f"unknown run_id: {run_id}")
            conn.execute(
                "UPDATE runs SET plan_materialized = 1, updated_at = ? WHERE run_id = ?",
                (now, run_id),
            )
            self._append_event(
                conn,
                run_id,
                "run.plan_materialized",
                actor,
                {"phase": row["phase"]},
                ts=now,
            )
            updated = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
            assert updated is not None
            return _row_to_run(updated)

    def transition_run_phase(
        self,
        run_id: str,
        to_phase: RunPhase,
        *,
        actor: str = "coordinator",
        reason: str | None = None,
        error_message: str | None = None,
        force: bool = False,
    ) -> RunRecord:
        now = utc_iso()
        with self._txn() as conn:
            row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
            if row is None:
                raise IllegalTransitionError(f"unknown run_id: {run_id}")
            current = RunPhase(row["phase"])
            if current == to_phase:
                return _row_to_run(row)
            if not force and to_phase not in LEGAL_PHASE_TRANSITIONS[current]:
                raise IllegalTransitionError(
                    f"illegal run phase transition {current} -> {to_phase}"
                )

            if to_phase == RunPhase.COMPLETED and not force:
                if not bool(row["plan_materialized"]):
                    raise IllegalTransitionError(
                        "cannot complete run before plan_materialized=1"
                    )
                unfinished = conn.execute(
                    """
                    SELECT COUNT(*) AS c FROM tasks
                    WHERE run_id = ? AND status IN ('pending', 'ready', 'running', 'paused')
                    """,
                    (run_id,),
                ).fetchone()
                if unfinished is not None and int(unfinished["c"]) > 0:
                    raise IllegalTransitionError(
                        f"cannot complete run with {unfinished['c']} non-terminal tasks"
                    )

            finished_at = (
                now
                if to_phase in (RunPhase.COMPLETED, RunPhase.FAILED, RunPhase.CANCELLED)
                else row["finished_at"]
            )
            err_msg = error_message if error_message is not None else row["error_message"]
            conn.execute(
                """
                UPDATE runs
                SET phase = ?, error_message = ?, updated_at = ?, finished_at = ?
                WHERE run_id = ?
                """,
                (to_phase, err_msg, now, finished_at, run_id),
            )
            self._append_event(
                conn,
                run_id,
                "run.phase_changed",
                actor,
                {
                    "from_phase": current,
                    "to_phase": to_phase,
                    "reason": reason,
                    "error_message": error_message,
                },
                ts=now,
            )
            updated = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
            assert updated is not None
            return _row_to_run(updated)

    def update_run_disk_bytes(self, run_id: str, disk_bytes: int) -> None:
        now = utc_iso()
        with self._txn() as conn:
            conn.execute(
                "UPDATE runs SET disk_bytes = ?, updated_at = ? WHERE run_id = ?",
                (int(disk_bytes), now, run_id),
            )

    def add_task(
        self,
        run_id: str,
        title: str,
        prompt: str,
        *,
        task_id: str | None = None,
        kind: TaskKind = TaskKind.WORK,
        role: str = "worker",
        tier: str = "default",
        priority: int = 0,
        max_retries: int = 2,
        budget: TaskBudget | None = None,
        depends_on: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        actor: str = "coordinator",
    ) -> TaskRecord:
        tid = task_id or f"tsk_{uuid.uuid4().hex[:12]}"
        deps = list(dict.fromkeys(depends_on or []))
        now = utc_iso()
        budget_json = json.dumps((budget or TaskBudget()).to_dict(), sort_keys=True)
        meta_json = json.dumps(metadata or {}, sort_keys=True)

        with self._txn() as conn:
            if tid in deps:
                raise IllegalTransitionError(f"task {tid} cannot depend on itself")
            existing = conn.execute("SELECT 1 FROM tasks WHERE task_id = ?", (tid,)).fetchone()
            if existing is not None:
                raise IllegalTransitionError(f"duplicate task_id: {tid}")

            dep_statuses: list[str] = []
            for dep_id in deps:
                dep_row = conn.execute(
                    "SELECT run_id, status FROM tasks WHERE task_id = ?",
                    (dep_id,),
                ).fetchone()
                if dep_row is None or dep_row["run_id"] != run_id:
                    raise IllegalTransitionError(
                        f"unknown dependency {dep_id} for run {run_id}"
                    )
                dep_statuses.append(dep_row["status"])

            if any(
                s in (TaskStatus.FAILED, TaskStatus.BLOCKED, TaskStatus.CANCELLED)
                for s in dep_statuses
            ):
                initial_status = TaskStatus.BLOCKED
            elif all(s == TaskStatus.COMPLETED for s in dep_statuses):
                initial_status = TaskStatus.READY
            else:
                initial_status = TaskStatus.PENDING

            conn.execute(
                """
                INSERT INTO tasks (
                    task_id, run_id, title, kind, prompt, role, tier, status,
                    priority, generation, active_attempt_id, max_retries, retry_count,
                    last_error_sig, consecutive_same_error, budget_json, metadata_json,
                    result_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, ?, 0, NULL, 0, ?, ?, NULL, ?, ?)
                """,
                (
                    tid,
                    run_id,
                    title,
                    kind,
                    prompt,
                    role,
                    tier,
                    initial_status,
                    priority,
                    max_retries,
                    budget_json,
                    meta_json,
                    now,
                    now,
                ),
            )
            for dep_id in deps:
                conn.execute(
                    "INSERT INTO task_deps (task_id, depends_on_task_id) VALUES (?, ?)",
                    (tid, dep_id),
                )
            self._append_event(
                conn,
                run_id,
                "task.created",
                actor,
                {
                    "task_id": tid,
                    "title": title,
                    "kind": kind,
                    "role": role,
                    "tier": tier,
                    "status": initial_status,
                    "depends_on": deps,
                },
                ts=now,
            )
            row = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (tid,)).fetchone()
            assert row is not None
            return _row_to_task(row)

    def add_dependency(self, task_id: str, depends_on_task_id: str) -> None:
        """Add a DAG edge while enforcing acyclicity."""
        if task_id == depends_on_task_id:
            raise IllegalTransitionError("self dependency is illegal")
        now = utc_iso()
        with self._txn() as conn:
            t1 = conn.execute("SELECT run_id, status FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
            t2 = conn.execute(
                "SELECT run_id, status FROM tasks WHERE task_id = ?", (depends_on_task_id,)
            ).fetchone()
            if t1 is None or t2 is None or t1["run_id"] != t2["run_id"]:
                raise IllegalTransitionError("tasks must belong to the same run")

            # Cycle check: is task_id reachable from depends_on_task_id via existing dependencies?
            stack = [depends_on_task_id]
            visited: set[str] = set()
            while stack:
                cur = stack.pop()
                if cur == task_id:
                    raise IllegalTransitionError(
                        f"dependency {task_id} -> {depends_on_task_id} introduces a cycle"
                    )
                if cur in visited:
                    continue
                visited.add(cur)
                rows = conn.execute(
                    "SELECT depends_on_task_id FROM task_deps WHERE task_id = ?",
                    (cur,),
                ).fetchall()
                stack.extend(r["depends_on_task_id"] for r in rows)

            conn.execute(
                "INSERT OR IGNORE INTO task_deps (task_id, depends_on_task_id) VALUES (?, ?)",
                (task_id, depends_on_task_id),
            )
            if t1["status"] == TaskStatus.READY and t2["status"] != TaskStatus.COMPLETED:
                conn.execute(
                    "UPDATE tasks SET status = ?, updated_at = ? WHERE task_id = ?",
                    (TaskStatus.PENDING, now, task_id),
                )
            self._append_event(
                conn,
                t1["run_id"],
                "task.dependency_added",
                "coordinator",
                {"task_id": task_id, "depends_on_task_id": depends_on_task_id},
                ts=now,
            )

    def get_task(self, task_id: str) -> TaskRecord | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
            return _row_to_task(row) if row is not None else None

    def list_tasks(self, run_id: str) -> list[TaskRecord]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM tasks WHERE run_id = ? ORDER BY created_at ASC, task_id ASC",
                (run_id,),
            ).fetchall()
            return [_row_to_task(r) for r in rows]

    def pause_task(self, task_id: str, *, actor: str = "operator", reason: str = "paused") -> TaskRecord:
        now = utc_iso()
        with self._txn() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
            if row is None:
                raise IllegalTransitionError(f"unknown task_id: {task_id}")
            status = TaskStatus(row["status"])
            if status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                raise IllegalTransitionError(f"cannot pause terminal task in state {status}")
            if status == TaskStatus.PAUSED:
                return _row_to_task(row)
            if status == TaskStatus.RUNNING and row["active_attempt_id"]:
                conn.execute(
                    """
                    UPDATE attempts
                    SET status = ?, error_message = ?, finished_at = ?
                    WHERE attempt_id = ? AND status IN ('starting', 'running')
                    """,
                    (AttemptStatus.INTERRUPTED, reason, now, row["active_attempt_id"]),
                )
            conn.execute(
                """
                UPDATE tasks
                SET status = ?, active_attempt_id = NULL, updated_at = ?
                WHERE task_id = ?
                """,
                (TaskStatus.PAUSED, now, task_id),
            )
            self._append_event(
                conn,
                row["run_id"],
                "task.paused",
                actor,
                {"task_id": task_id, "previous_status": status, "reason": reason},
                ts=now,
            )
            updated = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
            assert updated is not None
            return _row_to_task(updated)

    def resume_task(self, task_id: str, *, actor: str = "operator") -> TaskRecord:
        now = utc_iso()
        with self._txn() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
            if row is None:
                raise IllegalTransitionError(f"unknown task_id: {task_id}")
            if row["status"] != TaskStatus.PAUSED:
                raise IllegalTransitionError(f"task {task_id} is not paused (status={row['status']})")
            deps = conn.execute(
                """
                SELECT t.status
                FROM task_deps d
                JOIN tasks t ON t.task_id = d.depends_on_task_id
                WHERE d.task_id = ?
                """,
                (task_id,),
            ).fetchall()
            dep_statuses = [d["status"] for d in deps]
            if any(
                s in (TaskStatus.FAILED, TaskStatus.BLOCKED, TaskStatus.CANCELLED)
                for s in dep_statuses
            ):
                next_status = TaskStatus.BLOCKED
            elif all(s == TaskStatus.COMPLETED for s in dep_statuses):
                next_status = TaskStatus.READY
            else:
                next_status = TaskStatus.PENDING

            conn.execute(
                "UPDATE tasks SET status = ?, updated_at = ? WHERE task_id = ?",
                (next_status, now, task_id),
            )
            self._append_event(
                conn,
                row["run_id"],
                "task.resumed",
                actor,
                {"task_id": task_id, "status": next_status},
                ts=now,
            )
            updated = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
            assert updated is not None
            return _row_to_task(updated)

    def claim_next_task(
        self,
        run_id: str,
        worker_id: str,
        provider: str,
        model: str,
        *,
        lease_seconds: int = 120,
        kinds: tuple[TaskKind, ...] | None = None,
        route_resolver: Callable[[str, str], tuple[str, str]] | None = None,
    ) -> tuple[TaskRecord, AttemptRecord] | None:
        now_dt = utc_now()
        now = utc_iso(now_dt)
        lease_exp = utc_iso(now_dt + timedelta(seconds=lease_seconds))

        with self._txn() as conn:
            run_row = conn.execute("SELECT phase FROM runs WHERE run_id = ?", (run_id,)).fetchone()
            if run_row is None:
                return None
            if run_row["phase"] not in (RunPhase.PLANNING, RunPhase.RUNNING, RunPhase.VERIFYING):
                return None

            self._promote_and_block_pending(conn, run_id, now)

            if kinds:
                placeholders = ",".join("?" for _ in kinds)
                candidate = conn.execute(
                    f"""
                    SELECT * FROM tasks
                    WHERE run_id = ? AND status = 'ready' AND kind IN ({placeholders})
                    ORDER BY priority DESC, created_at ASC, task_id ASC
                    LIMIT 1
                    """,
                    (run_id, *[str(k) for k in kinds]),
                ).fetchone()
            else:
                candidate = conn.execute(
                    """
                    SELECT * FROM tasks
                    WHERE run_id = ? AND status = 'ready'
                    ORDER BY priority DESC, created_at ASC, task_id ASC
                    LIMIT 1
                    """,
                    (run_id,),
                ).fetchone()

            if candidate is None:
                return None

            chosen_provider, chosen_model = (
                route_resolver(str(candidate["role"]), str(candidate["tier"]))
                if route_resolver is not None
                else (provider, model)
            )
            old_gen = int(candidate["generation"])
            new_gen = old_gen + 1
            attempt_id = f"att_{uuid.uuid4().hex[:14]}"
            cur = conn.execute(
                """
                UPDATE tasks
                SET status = 'running',
                    generation = ?,
                    active_attempt_id = ?,
                    updated_at = ?
                WHERE task_id = ? AND status = 'ready' AND generation = ?
                """,
                (new_gen, attempt_id, now, candidate["task_id"], old_gen),
            )
            if cur.rowcount != 1:
                return None

            conn.execute(
                """
                INSERT INTO attempts (
                    attempt_id, run_id, task_id, generation, worker_id,
                    provider, model, status, pid, pgid, container_id,
                    lease_expires_at, input_tokens, output_tokens, total_tokens,
                    disk_bytes, error_kind, error_message, started_at, finished_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?, 0, 0, 0, 0, NULL, NULL, ?, NULL)
                """,
                (
                    attempt_id,
                    run_id,
                    candidate["task_id"],
                    new_gen,
                    worker_id,
                    chosen_provider,
                    chosen_model,
                    AttemptStatus.STARTING,
                    lease_exp,
                    now,
                ),
            )
            self._append_event(
                conn,
                run_id,
                "task.claimed",
                worker_id,
                {
                    "task_id": candidate["task_id"],
                    "attempt_id": attempt_id,
                    "generation": new_gen,
                    "provider": chosen_provider,
                    "model": chosen_model,
                    "lease_expires_at": lease_exp,
                },
                ts=now,
            )
            task_row = conn.execute(
                "SELECT * FROM tasks WHERE task_id = ?", (candidate["task_id"],)
            ).fetchone()
            att_row = conn.execute(
                "SELECT * FROM attempts WHERE attempt_id = ?", (attempt_id,)
            ).fetchone()
            assert task_row is not None and att_row is not None
            return _row_to_task(task_row), _row_to_attempt(att_row)

    def attach_attempt_runtime(
        self,
        task_id: str,
        attempt_id: str,
        generation: int,
        *,
        pid: int | None = None,
        pgid: int | None = None,
        container_id: str | None = None,
    ) -> AttemptRecord:
        now = utc_iso()
        with self._txn() as conn:
            self._assert_active_fence(conn, task_id, attempt_id, generation, actor="supervisor")
            conn.execute(
                """
                UPDATE attempts
                SET status = ?, pid = COALESCE(?, pid), pgid = COALESCE(?, pgid),
                    container_id = COALESCE(?, container_id)
                WHERE attempt_id = ?
                """,
                (AttemptStatus.RUNNING, pid, pgid, container_id, attempt_id),
            )
            row = conn.execute("SELECT * FROM attempts WHERE attempt_id = ?", (attempt_id,)).fetchone()
            assert row is not None
            self._append_event(
                conn,
                row["run_id"],
                "attempt.runtime_attached",
                "supervisor",
                {
                    "task_id": task_id,
                    "attempt_id": attempt_id,
                    "generation": generation,
                    "pid": pid,
                    "pgid": pgid,
                    "container_id": container_id,
                },
                ts=now,
            )
            return _row_to_attempt(row)

    def heartbeat_attempt(
        self,
        task_id: str,
        attempt_id: str,
        generation: int,
        *,
        lease_seconds: int = 120,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        total_tokens: int | None = None,
    ) -> AttemptRecord:
        now_dt = utc_now()
        now = utc_iso(now_dt)
        lease_exp = utc_iso(now_dt + timedelta(seconds=lease_seconds))
        with self._txn() as conn:
            self._assert_active_fence(conn, task_id, attempt_id, generation, actor="heartbeat")
            conn.execute(
                """
                UPDATE attempts
                SET status = ?,
                    lease_expires_at = ?,
                    input_tokens = COALESCE(?, input_tokens),
                    output_tokens = COALESCE(?, output_tokens),
                    total_tokens = COALESCE(?, total_tokens)
                WHERE attempt_id = ?
                """,
                (
                    AttemptStatus.RUNNING,
                    lease_exp,
                    input_tokens,
                    output_tokens,
                    total_tokens,
                    attempt_id,
                ),
            )
            row = conn.execute("SELECT * FROM attempts WHERE attempt_id = ?", (attempt_id,)).fetchone()
            assert row is not None
            return _row_to_attempt(row)

    def complete_attempt(
        self,
        task_id: str,
        attempt_id: str,
        generation: int,
        *,
        result: dict[str, Any] | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        total_tokens: int = 0,
        disk_bytes: int = 0,
    ) -> TaskRecord:
        now = utc_iso()
        eff_total = total_tokens or (input_tokens + output_tokens)
        with self._txn() as conn:
            task_row, _ = self._assert_active_fence(conn, task_id, attempt_id, generation)
            run_id = task_row["run_id"]
            conn.execute(
                """
                UPDATE attempts
                SET status = ?, input_tokens = ?, output_tokens = ?, total_tokens = ?,
                    disk_bytes = ?, error_kind = ?, finished_at = ?
                WHERE attempt_id = ?
                """,
                (
                    AttemptStatus.SUCCEEDED,
                    input_tokens,
                    output_tokens,
                    eff_total,
                    disk_bytes,
                    ErrorKind.NONE,
                    now,
                    attempt_id,
                ),
            )
            conn.execute(
                """
                UPDATE tasks
                SET status = ?, active_attempt_id = NULL, result_json = ?, updated_at = ?
                WHERE task_id = ? AND active_attempt_id = ? AND generation = ?
                """,
                (
                    TaskStatus.COMPLETED,
                    json.dumps(result or {}, sort_keys=True),
                    now,
                    task_id,
                    attempt_id,
                    generation,
                ),
            )
            conn.execute(
                "UPDATE runs SET tokens_used = tokens_used + ?, updated_at = ? WHERE run_id = ?",
                (eff_total, now, run_id),
            )
            self._append_event(
                conn,
                run_id,
                "attempt.completed",
                "worker",
                {
                    "task_id": task_id,
                    "attempt_id": attempt_id,
                    "generation": generation,
                    "total_tokens": eff_total,
                },
                ts=now,
            )
            self._promote_and_block_pending(conn, run_id, now)
            updated = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
            assert updated is not None
            return _row_to_task(updated)

    def fail_attempt(
        self,
        task_id: str,
        attempt_id: str,
        generation: int,
        *,
        error_kind: ErrorKind,
        error_message: str,
        error_sig: str = "",
        max_same_error_repeats: int = 2,
        input_tokens: int = 0,
        output_tokens: int = 0,
        total_tokens: int = 0,
        disk_bytes: int = 0,
        force_terminal: bool = False,
        cancelled: bool = False,
    ) -> TaskRecord:
        now = utc_iso()
        eff_total = total_tokens or (input_tokens + output_tokens)
        with self._txn() as conn:
            task_row, _ = self._assert_active_fence(conn, task_id, attempt_id, generation)
            run_id = task_row["run_id"]
            if cancelled:
                att_status = AttemptStatus.CANCELLED
            elif error_kind == ErrorKind.TIMEOUT:
                att_status = AttemptStatus.TIMED_OUT
            else:
                att_status = AttemptStatus.FAILED

            conn.execute(
                """
                UPDATE attempts
                SET status = ?, input_tokens = ?, output_tokens = ?, total_tokens = ?,
                    disk_bytes = ?, error_kind = ?, error_message = ?, finished_at = ?
                WHERE attempt_id = ?
                """,
                (
                    att_status,
                    input_tokens,
                    output_tokens,
                    eff_total,
                    disk_bytes,
                    error_kind,
                    error_message,
                    now,
                    attempt_id,
                ),
            )
            conn.execute(
                "UPDATE runs SET tokens_used = tokens_used + ?, updated_at = ? WHERE run_id = ?",
                (eff_total, now, run_id),
            )

            same_repeats = (
                int(task_row["consecutive_same_error"]) + 1
                if (error_sig and error_sig == task_row["last_error_sig"])
                else 1
            )
            stalled = (
                error_kind not in (ErrorKind.TRANSIENT, ErrorKind.QUOTA)
                and same_repeats >= max_same_error_repeats
            )
            can_retry = (
                not force_terminal
                and not cancelled
                and error_kind != ErrorKind.BUDGET_EXCEEDED
                and int(task_row["retry_count"]) < int(task_row["max_retries"])
                and not stalled
            )
            next_status = TaskStatus.READY if can_retry else (
                TaskStatus.CANCELLED if cancelled else TaskStatus.FAILED
            )
            next_retries = (
                int(task_row["retry_count"]) + 1 if can_retry else int(task_row["retry_count"])
            )

            conn.execute(
                """
                UPDATE tasks
                SET status = ?,
                    active_attempt_id = NULL,
                    retry_count = ?,
                    last_error_sig = ?,
                    consecutive_same_error = ?,
                    updated_at = ?
                WHERE task_id = ? AND active_attempt_id = ? AND generation = ?
                """,
                (
                    next_status,
                    next_retries,
                    error_sig or task_row["last_error_sig"],
                    same_repeats,
                    now,
                    task_id,
                    attempt_id,
                    generation,
                ),
            )
            self._append_event(
                conn,
                run_id,
                "attempt.failed",
                "worker",
                {
                    "task_id": task_id,
                    "attempt_id": attempt_id,
                    "generation": generation,
                    "error_kind": error_kind,
                    "error_message": error_message,
                    "requeued": can_retry,
                    "stalled": stalled,
                    "next_task_status": next_status,
                },
                ts=now,
            )
            if next_status in (TaskStatus.FAILED, TaskStatus.CANCELLED):
                self._promote_and_block_pending(conn, run_id, now)
            updated = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
            assert updated is not None
            return _row_to_task(updated)

    def interrupt_attempt(
        self,
        task_id: str,
        attempt_id: str,
        generation: int,
        *,
        reason: str = "interrupted",
        input_tokens: int = 0,
        output_tokens: int = 0,
        total_tokens: int = 0,
    ) -> TaskRecord:
        now = utc_iso()
        eff_total = total_tokens or (input_tokens + output_tokens)
        with self._txn() as conn:
            task_row, _ = self._assert_active_fence(
                conn, task_id, attempt_id, generation, actor="coordinator"
            )
            run_id = task_row["run_id"]
            conn.execute(
                """
                UPDATE attempts
                SET status = ?, input_tokens = ?, output_tokens = ?, total_tokens = ?,
                    error_message = ?, finished_at = ?
                WHERE attempt_id = ?
                """,
                (
                    AttemptStatus.INTERRUPTED,
                    input_tokens,
                    output_tokens,
                    eff_total,
                    reason,
                    now,
                    attempt_id,
                ),
            )
            conn.execute(
                """
                UPDATE tasks
                SET status = ?, active_attempt_id = NULL, updated_at = ?
                WHERE task_id = ? AND active_attempt_id = ? AND generation = ?
                """,
                (TaskStatus.READY, now, task_id, attempt_id, generation),
            )
            if eff_total:
                conn.execute(
                    "UPDATE runs SET tokens_used = tokens_used + ?, updated_at = ? WHERE run_id = ?",
                    (eff_total, now, run_id),
                )
            self._append_event(
                conn,
                run_id,
                "attempt.interrupted",
                "coordinator",
                {
                    "task_id": task_id,
                    "attempt_id": attempt_id,
                    "generation": generation,
                    "reason": reason,
                },
                ts=now,
            )
            updated = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
            assert updated is not None
            return _row_to_task(updated)

    def reclaim_expired_leases(
        self, run_id: str, *, now_iso: str | None = None
    ) -> list[AttemptRecord]:
        now = now_iso or utc_iso()
        reclaimed: list[AttemptRecord] = []
        with self._txn() as conn:
            expired = conn.execute(
                """
                SELECT a.*, t.retry_count, t.max_retries
                FROM attempts a
                JOIN tasks t ON t.task_id = a.task_id
                WHERE a.run_id = ?
                  AND a.status IN ('starting', 'running')
                  AND a.lease_expires_at <= ?
                  AND t.status = 'running'
                  AND t.active_attempt_id = a.attempt_id
                  AND t.generation = a.generation
                """,
                (run_id, now),
            ).fetchall()

            for row in expired:
                reclaimed.append(_row_to_attempt(row))
                conn.execute(
                    """
                    UPDATE attempts
                    SET status = ?, error_kind = ?, error_message = ?, finished_at = ?
                    WHERE attempt_id = ? AND status IN ('starting', 'running')
                    """,
                    (AttemptStatus.TIMED_OUT, ErrorKind.TIMEOUT, "lease expired", now, row["attempt_id"]),
                )
                can_retry = int(row["retry_count"]) < int(row["max_retries"])
                next_status = TaskStatus.READY if can_retry else TaskStatus.FAILED
                next_retries = int(row["retry_count"]) + (1 if can_retry else 0)
                conn.execute(
                    """
                    UPDATE tasks
                    SET status = ?, active_attempt_id = NULL, retry_count = ?, updated_at = ?
                    WHERE task_id = ? AND active_attempt_id = ? AND generation = ?
                    """,
                    (
                        next_status,
                        next_retries,
                        now,
                        row["task_id"],
                        row["attempt_id"],
                        row["generation"],
                    ),
                )
                self._append_event(
                    conn,
                    run_id,
                    "attempt.lease_expired",
                    "coordinator",
                    {
                        "task_id": row["task_id"],
                        "attempt_id": row["attempt_id"],
                        "generation": int(row["generation"]),
                        "pgid": row["pgid"],
                        "container_id": row["container_id"],
                        "requeued": can_retry,
                    },
                    ts=now,
                )
            if reclaimed:
                self._promote_and_block_pending(conn, run_id, now)
        return reclaimed

    def recover_run(self, run_id: str) -> list[AttemptRecord]:
        """Reconcile any leftover running attempts/tasks from a previous crash without auto-completing."""
        now = utc_iso()
        interrupted_attempts: list[AttemptRecord] = []
        with self._txn() as conn:
            run_row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
            if run_row is None:
                raise IllegalTransitionError(f"unknown run_id: {run_id}")

            stale_attempts = conn.execute(
                """
                SELECT * FROM attempts
                WHERE run_id = ? AND status IN ('starting', 'running')
                """,
                (run_id,),
            ).fetchall()
            for row in stale_attempts:
                interrupted_attempts.append(_row_to_attempt(row))
                conn.execute(
                    """
                    UPDATE attempts
                    SET status = ?, error_message = ?, finished_at = ?
                    WHERE attempt_id = ?
                    """,
                    (
                        AttemptStatus.INTERRUPTED,
                        "reconciled on coordinator recovery",
                        now,
                        row["attempt_id"],
                    ),
                )

            stale_tasks = conn.execute(
                "SELECT task_id FROM tasks WHERE run_id = ? AND status = ?",
                (run_id, TaskStatus.RUNNING),
            ).fetchall()
            for t_row in stale_tasks:
                conn.execute(
                    """
                    UPDATE tasks
                    SET status = ?, active_attempt_id = NULL, updated_at = ?
                    WHERE task_id = ? AND status = ?
                    """,
                    (TaskStatus.READY, now, t_row["task_id"], TaskStatus.RUNNING),
                )

            self._promote_and_block_pending(conn, run_id, now)
            self._append_event(
                conn,
                run_id,
                "recovery.reconciled",
                "coordinator",
                {
                    "phase": run_row["phase"],
                    "plan_materialized": bool(run_row["plan_materialized"]),
                    "interrupted_attempt_ids": [a.attempt_id for a in interrupted_attempts],
                    "requeued_task_ids": [r["task_id"] for r in stale_tasks],
                },
                ts=now,
            )
        return interrupted_attempts

    def get_attempt(self, attempt_id: str) -> AttemptRecord | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM attempts WHERE attempt_id = ?", (attempt_id,)
            ).fetchone()
            return _row_to_attempt(row) if row is not None else None

    def list_attempts(self, run_id: str, task_id: str | None = None) -> list[AttemptRecord]:
        with self._lock:
            if task_id:
                rows = self._conn.execute(
                    "SELECT * FROM attempts WHERE run_id = ? AND task_id = ? ORDER BY generation ASC",
                    (run_id, task_id),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM attempts WHERE run_id = ? ORDER BY started_at ASC",
                    (run_id,),
                ).fetchall()
            return [_row_to_attempt(r) for r in rows]

    def add_blackboard_entry(
        self,
        run_id: str,
        kind: BlackboardKind,
        title: str,
        body: str,
        fingerprint: str,
        *,
        task_id: str | None = None,
        attempt_id: str | None = None,
        generation: int | None = None,
        tags: list[str] | None = None,
        confidence: float = 0.5,
        supersedes_id: str | None = None,
        deduplicate: bool = True,
    ) -> tuple[BlackboardEntry, bool]:
        now = utc_iso()
        with self._txn() as conn:
            if attempt_id is not None:
                if task_id is None or generation is None:
                    raise FencedAttemptError("task_id and generation required with attempt_id")
                self._assert_active_fence(
                    conn, task_id, attempt_id, generation, actor="blackboard"
                )

            if deduplicate:
                existing = conn.execute(
                    """
                    SELECT * FROM blackboard_entries
                    WHERE run_id = ? AND fingerprint = ?
                    LIMIT 1
                    """,
                    (run_id, fingerprint),
                ).fetchone()
                if existing is not None:
                    return _row_to_bb(existing), True

            entry_id = f"bb_{uuid.uuid4().hex[:14]}"
            tags_json = json.dumps(tags or [], sort_keys=True)
            conn.execute(
                """
                INSERT INTO blackboard_entries (
                    entry_id, run_id, task_id, attempt_id, generation,
                    kind, title, body, tags_json, fingerprint, confidence,
                    supersedes_id, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry_id,
                    run_id,
                    task_id,
                    attempt_id,
                    generation,
                    kind,
                    title,
                    body,
                    tags_json,
                    fingerprint,
                    float(confidence),
                    supersedes_id,
                    now,
                ),
            )
            self._append_event(
                conn,
                run_id,
                "blackboard.published",
                attempt_id or "coordinator",
                {
                    "entry_id": entry_id,
                    "task_id": task_id,
                    "kind": kind,
                    "title": title,
                    "fingerprint": fingerprint,
                },
                ts=now,
            )
            row = conn.execute(
                "SELECT * FROM blackboard_entries WHERE entry_id = ?", (entry_id,)
            ).fetchone()
            assert row is not None
            return _row_to_bb(row), False

    def list_blackboard_entries(
        self, run_id: str, *, kind: BlackboardKind | None = None
    ) -> list[BlackboardEntry]:
        with self._lock:
            if kind is not None:
                rows = self._conn.execute(
                    """
                    SELECT * FROM blackboard_entries
                    WHERE run_id = ? AND kind = ?
                    ORDER BY created_at ASC, entry_id ASC
                    """,
                    (run_id, kind),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    """
                    SELECT * FROM blackboard_entries
                    WHERE run_id = ?
                    ORDER BY created_at ASC, entry_id ASC
                    """,
                    (run_id,),
                ).fetchall()
            return [_row_to_bb(r) for r in rows]

    def record_artifact(
        self,
        run_id: str,
        sha256: str,
        rel_path: str,
        size_bytes: int,
        *,
        source_path: str | None = None,
        task_id: str | None = None,
        attempt_id: str | None = None,
        media_type: str = "application/octet-stream",
        metadata: dict[str, Any] | None = None,
    ) -> tuple[ArtifactRecord, bool]:
        now = utc_iso()
        with self._txn() as conn:
            existing = conn.execute(
                "SELECT * FROM artifacts WHERE run_id = ? AND sha256 = ? LIMIT 1",
                (run_id, sha256),
            ).fetchone()
            if existing is not None:
                return _row_to_artifact(existing), True
            art_id = f"art_{uuid.uuid4().hex[:14]}"
            conn.execute(
                """
                INSERT INTO artifacts (
                    artifact_id, run_id, task_id, attempt_id, sha256, rel_path,
                    source_path, size_bytes, media_type, metadata_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    art_id,
                    run_id,
                    task_id,
                    attempt_id,
                    sha256,
                    rel_path,
                    source_path,
                    int(size_bytes),
                    media_type,
                    json.dumps(metadata or {}, sort_keys=True),
                    now,
                ),
            )
            self._append_event(
                conn,
                run_id,
                "artifact.recorded",
                attempt_id or "coordinator",
                {
                    "artifact_id": art_id,
                    "sha256": sha256,
                    "rel_path": rel_path,
                    "size_bytes": int(size_bytes),
                },
                ts=now,
            )
            row = conn.execute(
                "SELECT * FROM artifacts WHERE artifact_id = ?", (art_id,)
            ).fetchone()
            assert row is not None
            return _row_to_artifact(row), False

    def list_artifacts(self, run_id: str) -> list[ArtifactRecord]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM artifacts WHERE run_id = ? ORDER BY created_at ASC",
                (run_id,),
            ).fetchall()
            return [_row_to_artifact(r) for r in rows]

    def record_diversity_assignment(
        self,
        run_id: str,
        task_id: str,
        generation: int,
        persona: str,
        kb_item_ids: list[str],
        angle_seed: int,
    ) -> DiversityAssignment:
        now = utc_iso()
        with self._txn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO diversity_assignments (
                    run_id, task_id, generation, persona, kb_item_ids_json, angle_seed, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    task_id,
                    int(generation),
                    persona,
                    json.dumps(kb_item_ids),
                    int(angle_seed),
                    now,
                ),
            )
            self._append_event(
                conn,
                run_id,
                "diversity.assigned",
                "coordinator",
                {
                    "task_id": task_id,
                    "generation": int(generation),
                    "persona": persona,
                    "kb_item_ids": kb_item_ids,
                    "angle_seed": int(angle_seed),
                },
                ts=now,
            )
        return DiversityAssignment(
            run_id=run_id,
            task_id=task_id,
            generation=int(generation),
            persona=persona,
            kb_item_ids=list(kb_item_ids),
            angle_seed=int(angle_seed),
            created_at=now,
        )

    def list_diversity_assignments(self, run_id: str) -> list[DiversityAssignment]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM diversity_assignments WHERE run_id = ? ORDER BY created_at ASC",
                (run_id,),
            ).fetchall()
            return [
                DiversityAssignment(
                    run_id=r["run_id"],
                    task_id=r["task_id"],
                    generation=int(r["generation"]),
                    persona=r["persona"],
                    kb_item_ids=json.loads(r["kb_item_ids_json"]),
                    angle_seed=int(r["angle_seed"]),
                    created_at=r["created_at"],
                )
                for r in rows
            ]

    def list_events(self, run_id: str, *, after_seq: int = 0) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT seq, run_id, ts, event_type, actor, payload_json
                FROM events
                WHERE run_id = ? AND seq > ?
                ORDER BY seq ASC
                """,
                (run_id, int(after_seq)),
            ).fetchall()
            return [
                {
                    "seq": int(r["seq"]),
                    "run_id": r["run_id"],
                    "ts": r["ts"],
                    "event_type": r["event_type"],
                    "actor": r["actor"],
                    "payload": json.loads(r["payload_json"]),
                }
                for r in rows
            ]
