"""Core domain models, state enums, and typed orchestration exceptions."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class RunPhase(StrEnum):
    INIT = "init"
    PLANNING = "planning"
    RUNNING = "running"
    VERIFYING = "verifying"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class TaskKind(StrEnum):
    PLAN = "plan"
    WORK = "work"
    VERIFY = "verify"
    SYNTHESIZE = "synthesize"


class AttemptStatus(StrEnum):
    STARTING = "starting"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    FENCED = "fenced"
    INTERRUPTED = "interrupted"
    CANCELLED = "cancelled"


class ErrorKind(StrEnum):
    NONE = "none"
    TRANSIENT = "transient"
    QUOTA = "quota"
    BUDGET_EXCEEDED = "budget_exceeded"
    TIMEOUT = "timeout"
    FENCED = "fenced"
    HARD_ERROR = "hard_error"


class BlackboardKind(StrEnum):
    FACT = "fact"
    HYPOTHESIS = "hypothesis"
    FINDING = "finding"
    NOTE = "note"
    SYNTHESIS = "synthesis"
    ARTIFACT_REF = "artifact_ref"


class OrchestratorError(Exception):
    """Base error for orchestrator runtime failures."""


class CoordinatorLockError(OrchestratorError):
    """Raised when another coordinator process holds the exclusive state lock."""


class FencedAttemptError(OrchestratorError):
    """Raised when a stale attempt or generation attempts a state or blackboard write."""


class IllegalTransitionError(OrchestratorError):
    """Raised when an invalid run phase or task transition is attempted."""


class BudgetExceededError(OrchestratorError):
    """Raised when run or attempt token, wall-time, memory, or disk budgets are exceeded."""


@dataclass(slots=True)
class TaskBudget:
    max_tokens: int = 100_000
    max_wall_seconds: float = 300.0
    max_memory_mb: int = 2048
    max_disk_bytes: int = 256 * 1024 * 1024
    max_output_bytes: int = 2 * 1024 * 1024

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_tokens": self.max_tokens,
            "max_wall_seconds": self.max_wall_seconds,
            "max_memory_mb": self.max_memory_mb,
            "max_disk_bytes": self.max_disk_bytes,
            "max_output_bytes": self.max_output_bytes,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> TaskBudget:
        if not raw:
            return cls()
        return cls(
            max_tokens=int(raw.get("max_tokens", 100_000)),
            max_wall_seconds=float(raw.get("max_wall_seconds", 300.0)),
            max_memory_mb=int(raw.get("max_memory_mb", 2048)),
            max_disk_bytes=int(raw.get("max_disk_bytes", 256 * 1024 * 1024)),
            max_output_bytes=int(raw.get("max_output_bytes", 2 * 1024 * 1024)),
        )


@dataclass(slots=True)
class RunBudget:
    max_tokens: int = 2_000_000
    max_wall_seconds: float = 3600.0
    max_disk_bytes: int = 2 * 1024 * 1024 * 1024
    min_free_disk_bytes: int = 256 * 1024 * 1024

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_tokens": self.max_tokens,
            "max_wall_seconds": self.max_wall_seconds,
            "max_disk_bytes": self.max_disk_bytes,
            "min_free_disk_bytes": self.min_free_disk_bytes,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> RunBudget:
        if not raw:
            return cls()
        return cls(
            max_tokens=int(raw.get("max_tokens", 2_000_000)),
            max_wall_seconds=float(raw.get("max_wall_seconds", 3600.0)),
            max_disk_bytes=int(raw.get("max_disk_bytes", 2 * 1024 * 1024 * 1024)),
            min_free_disk_bytes=int(raw.get("min_free_disk_bytes", 256 * 1024 * 1024)),
        )


@dataclass(slots=True)
class McpServerConfig:
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    timeout_seconds: float = 60.0
    max_result_bytes: int = 256 * 1024
    enabled: bool = True


@dataclass(slots=True)
class RouteTarget:
    provider: str
    model: str
    tier: str = "default"
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RunRecord:
    run_id: str
    goal: str
    phase: RunPhase
    plan_materialized: bool
    seed: int
    config_json: str
    budget_json: str
    tokens_used: int
    disk_bytes: int
    drost_engagement_id: str | None
    error_message: str | None
    created_at: str
    updated_at: str
    finished_at: str | None


@dataclass(slots=True)
class TaskRecord:
    task_id: str
    run_id: str
    title: str
    kind: TaskKind
    prompt: str
    role: str
    tier: str
    status: TaskStatus
    priority: int
    generation: int
    active_attempt_id: str | None
    max_retries: int
    retry_count: int
    last_error_sig: str | None
    consecutive_same_error: int
    budget_json: str
    metadata_json: str
    result_json: str | None
    created_at: str
    updated_at: str


@dataclass(slots=True)
class AttemptRecord:
    attempt_id: str
    run_id: str
    task_id: str
    generation: int
    worker_id: str
    provider: str
    model: str
    status: AttemptStatus
    pid: int | None
    pgid: int | None
    container_id: str | None
    lease_expires_at: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    disk_bytes: int
    error_kind: ErrorKind | None
    error_message: str | None
    started_at: str
    finished_at: str | None


@dataclass(slots=True)
class BlackboardEntry:
    entry_id: str
    run_id: str
    task_id: str | None
    attempt_id: str | None
    generation: int | None
    kind: BlackboardKind
    title: str
    body: str
    tags: list[str]
    fingerprint: str
    confidence: float
    supersedes_id: str | None
    created_at: str


@dataclass(slots=True)
class ArtifactRecord:
    artifact_id: str
    run_id: str
    task_id: str | None
    attempt_id: str | None
    sha256: str
    rel_path: str
    source_path: str | None
    size_bytes: int
    media_type: str
    metadata: dict[str, Any]
    created_at: str


@dataclass(slots=True)
class DiversityAssignment:
    run_id: str
    task_id: str
    generation: int
    persona: str
    kb_item_ids: list[str]
    angle_seed: int
    created_at: str
    instructions: str = ""
    kb_items: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class FollowUpProposal:
    title: str
    prompt: str
    kind: TaskKind = TaskKind.WORK
    role: str = "worker"
    tier: str = "default"
    priority: int = 0
    depends_on_titles: list[str] = field(default_factory=list)


@dataclass(slots=True)
class WorkerOutput:
    status: str
    summary: str
    facts: list[dict[str, Any]] = field(default_factory=list)
    hypotheses: list[dict[str, Any]] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)
    notes: list[dict[str, Any]] = field(default_factory=list)
    follow_up_tasks: list[FollowUpProposal] = field(default_factory=list)
    blocker_reason: str | None = None
    raw_text: str = ""


@dataclass(slots=True)
class AttemptResult:
    success: bool
    output: WorkerOutput | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    error_kind: ErrorKind = ErrorKind.NONE
    error_message: str | None = None
    timed_out: bool = False
    cancelled: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
