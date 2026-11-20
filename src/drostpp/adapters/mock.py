"""Deterministic mock adapter for offline integration, chaos, and smoke tests."""

from __future__ import annotations

from typing import Callable

from ..models import AttemptResult, ErrorKind, FollowUpProposal, TaskKind, WorkerOutput
from .base import AttemptContext


class MockAdapter:
    """Executes deterministic scripted behaviors or default synthetic plan/work/verify outputs."""

    def __init__(
        self,
        handler: Callable[[AttemptContext], AttemptResult] | None = None,
    ) -> None:
        self.handler = handler
        self.calls: list[tuple[str, str, int, str]] = []

    def execute(self, ctx: AttemptContext) -> AttemptResult:
        self.calls.append((ctx.task.task_id, ctx.attempt.attempt_id, ctx.attempt.generation, ctx.route.provider))
        if self.handler is not None:
            return self.handler(ctx)

        if ctx.task.kind == TaskKind.PLAN:
            return AttemptResult(
                success=True,
                output=WorkerOutput(
                    status="completed",
                    summary=f"Decomposed goal into two bounded work items for {ctx.task.title}.",
                    facts=[
                        {
                            "title": "Plan materialized",
                            "body": f"Initial decomposition generated for: {ctx.task.title}",
                            "tags": ["plan"],
                            "confidence": 0.9,
                        }
                    ],
                    follow_up_tasks=[
                        FollowUpProposal(
                            title="Analyze primary constraints",
                            prompt="Inspect system constraints and record verified facts.",
                            kind=TaskKind.WORK,
                            role="analyst",
                            tier="default",
                            priority=10,
                        ),
                        FollowUpProposal(
                            title="Explore edge cases",
                            prompt="Explore boundary conditions and failure modes.",
                            kind=TaskKind.WORK,
                            role="auditor",
                            tier="default",
                            priority=5,
                        ),
                    ],
                ),
                input_tokens=120,
                output_tokens=180,
                total_tokens=300,
                error_kind=ErrorKind.NONE,
            )

        if ctx.task.kind == TaskKind.VERIFY:
            return AttemptResult(
                success=True,
                output=WorkerOutput(
                    status="completed",
                    summary="Verification confirmed all recorded findings are grounded on the blackboard.",
                    notes=[
                        {
                            "title": "Verification summary",
                            "body": "Checked blackboard facts and findings for consistency.",
                            "tags": ["verify"],
                            "confidence": 0.95,
                        }
                    ],
                ),
                input_tokens=90,
                output_tokens=110,
                total_tokens=200,
                error_kind=ErrorKind.NONE,
            )

        return AttemptResult(
            success=True,
            output=WorkerOutput(
                status="completed",
                summary=f"Completed task '{ctx.task.title}' (gen={ctx.attempt.generation}).",
                facts=[
                    {
                        "title": f"Observation from {ctx.task.title}",
                        "body": f"Recorded structured result during attempt {ctx.attempt.attempt_id}.",
                        "tags": ["mock", ctx.task.role],
                        "confidence": 0.85,
                    }
                ],
                findings=[
                    {
                        "title": f"Verified output for {ctx.task.title}",
                        "body": f"Deterministic finding produced for task {ctx.task.task_id}.",
                        "tags": [ctx.task.role],
                        "confidence": 0.8,
                    }
                ],
            ),
            input_tokens=100,
            output_tokens=150,
            total_tokens=250,
            error_kind=ErrorKind.NONE,
        )
