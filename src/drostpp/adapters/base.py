"""Shared worker adapter protocol, prompt context, output JSON schema, and robust parsing."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
import threading
from typing import Any, Callable, Protocol

from ..models import (
    AttemptRecord,
    AttemptResult,
    ErrorKind,
    FollowUpProposal,
    McpServerConfig,
    ResourceHandoff,
    RouteTarget,
    TaskBudget,
    TaskKind,
    TaskRecord,
    WorkerOutput,
)

WORKER_OUTPUT_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "status",
        "summary",
        "facts",
        "hypotheses",
        "findings",
        "notes",
        "follow_up_tasks",
        "resource_handoffs",
        "blocker_reason",
    ],
    "properties": {
        "status": {
            "type": "string",
            "enum": ["completed", "blocked", "needs_follow_up"],
        },
        "summary": {"type": "string"},
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["title", "body", "tags", "confidence"],
                "properties": {
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "number"},
                },
            },
        },
        "hypotheses": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["title", "body", "tags", "confidence"],
                "properties": {
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "number"},
                },
            },
        },
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["title", "body", "tags", "confidence"],
                "properties": {
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "number"},
                },
            },
        },
        "notes": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["title", "body", "tags", "confidence"],
                "properties": {
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "number"},
                },
            },
        },
        "follow_up_tasks": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "title",
                    "prompt",
                    "kind",
                    "role",
                    "tier",
                    "priority",
                    "depends_on_titles",
                ],
                "properties": {
                    "title": {"type": "string"},
                    "prompt": {"type": "string"},
                    "kind": {
                        "type": "string",
                        "enum": ["work", "verify", "synthesize"],
                    },
                    "role": {"type": "string"},
                    "tier": {"type": "string"},
                    "priority": {"type": "integer"},
                    "depends_on_titles": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            },
        },
        "resource_handoffs": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["resource_key", "to_task_title"],
                "properties": {
                    "resource_key": {"type": "string"},
                    "to_task_title": {"type": "string"},
                },
            },
        },
        "blocker_reason": {"type": ["string", "null"]},
    },
}

_FENCED_BLOCK_RE = re.compile(r"```(?:json)?\s*\n(.*?)\n```", re.DOTALL | re.IGNORECASE)


@dataclass(slots=True)
class AttemptContext:
    run_id: str
    task: TaskRecord
    attempt: AttemptRecord
    prompt: str
    attempt_dir: Path
    workspace_dir: Path | None
    budget: TaskBudget
    route: RouteTarget
    mcp_servers: list[McpServerConfig] = field(default_factory=list)
    cancel_event: threading.Event = field(default_factory=threading.Event)
    on_runtime_attached: Callable[[int | None, int | None, str | None], None] | None = None
    on_heartbeat: Callable[[int | None, int | None, int | None], None] | None = None
    env: dict[str, str] = field(default_factory=dict)


class WorkerAdapter(Protocol):
    def execute(self, ctx: AttemptContext) -> AttemptResult:
        """Execute one fenced worker attempt and return an AttemptResult."""


def classify_error_text(text: str) -> ErrorKind:
    lower = text.lower()
    if any(
        tok in lower
        for tok in (
            "insufficient_quota",
            "quota exceeded",
            "rate limit",
            "rate_limit",
            "http 429",
            "status 429",
            "too many requests",
        )
    ):
        return ErrorKind.QUOTA
    if any(
        tok in lower
        for tok in (
            "timed out",
            "timeout",
            "econnreset",
            "connection reset",
            "temporarily unavailable",
            "502 bad gateway",
            "503 service",
            "504 gateway",
        )
    ):
        return ErrorKind.TRANSIENT
    return ErrorKind.HARD_ERROR


def _extract_json_dict(raw_text: str) -> dict[str, Any] | None:
    stripped = raw_text.strip()
    if not stripped:
        return None
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    for block in reversed(_FENCED_BLOCK_RE.findall(stripped)):
        try:
            parsed = json.loads(block.strip())
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue

    # Last-resort balanced brace scan from the end of the text.
    decoder = json.JSONDecoder()
    for idx in range(len(stripped) - 1, -1, -1):
        if stripped[idx] != "{":
            continue
        try:
            obj, _end = decoder.raw_decode(stripped[idx:])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue
    return None


def _normalize_bb_items(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict):
            title = str(item.get("title") or "").strip()
            body = str(item.get("body") or "").strip()
            if not title and not body:
                continue
            tags_raw = item.get("tags")
            tags = (
                [str(t).strip() for t in tags_raw if str(t).strip()]
                if isinstance(tags_raw, list)
                else []
            )
            try:
                conf = float(item.get("confidence", 0.6))
            except (TypeError, ValueError):
                conf = 0.6
            out.append(
                {
                    "title": title or body[:80],
                    "body": body or title,
                    "tags": tags,
                    "confidence": max(0.0, min(1.0, conf)),
                }
            )
        elif isinstance(item, str) and item.strip():
            s = item.strip()
            out.append({"title": s[:80], "body": s, "tags": [], "confidence": 0.5})
    return out


def _normalize_follow_ups(raw: Any) -> list[FollowUpProposal]:
    if not isinstance(raw, list):
        return []
    proposals: list[FollowUpProposal] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        prompt = str(item.get("prompt") or "").strip()
        if not title or not prompt:
            continue
        raw_kind = str(item.get("kind", "work")).lower()
        kind = TaskKind(raw_kind) if raw_kind in {"work", "verify", "synthesize"} else TaskKind.WORK
        deps_raw = item.get("depends_on_titles") or []
        deps = (
            [str(d).strip() for d in deps_raw if str(d).strip()]
            if isinstance(deps_raw, list)
            else []
        )
        try:
            priority = int(item.get("priority", 0))
        except (TypeError, ValueError):
            priority = 0
        proposals.append(
            FollowUpProposal(
                title=title[:160],
                prompt=prompt,
                kind=kind,
                role=str(item.get("role") or "worker").strip(),
                tier=str(item.get("tier") or "default").strip(),
                priority=priority,
                depends_on_titles=deps,
            )
        )
    return proposals


def _normalize_resource_handoffs(raw: Any) -> list[ResourceHandoff]:
    if not isinstance(raw, list):
        return []
    handoffs: list[ResourceHandoff] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        resource_key = str(item.get("resource_key") or "").strip()
        to_task_title = str(item.get("to_task_title") or "").strip()
        if resource_key and to_task_title:
            handoffs.append(
                ResourceHandoff(
                    resource_key=resource_key[:80],
                    to_task_title=to_task_title[:160],
                )
            )
    return handoffs


def parse_worker_output(raw_text: str) -> WorkerOutput:
    """Parse structured WorkerOutput JSON or gracefully wrap plain-text responses."""
    data = _extract_json_dict(raw_text)
    if data is None:
        cleaned = raw_text.strip()
        return WorkerOutput(
            status="completed",
            summary=cleaned[:1500] if cleaned else "Completed with empty text output.",
            notes=(
                [{"title": "Worker Text Output", "body": cleaned[:4000], "tags": [], "confidence": 0.5}]
                if cleaned
                else []
            ),
            raw_text=raw_text,
        )

    status = str(data.get("status") or "completed").strip().lower()
    if status not in {"completed", "blocked", "needs_follow_up"}:
        status = "completed"
    summary = str(data.get("summary") or "").strip() or status
    blocker_reason = data.get("blocker_reason")
    return WorkerOutput(
        status=status,
        summary=summary,
        facts=_normalize_bb_items(data.get("facts")),
        hypotheses=_normalize_bb_items(data.get("hypotheses")),
        findings=_normalize_bb_items(data.get("findings")),
        notes=_normalize_bb_items(data.get("notes")),
        follow_up_tasks=_normalize_follow_ups(data.get("follow_up_tasks")),
        resource_handoffs=_normalize_resource_handoffs(data.get("resource_handoffs")),
        blocker_reason=str(blocker_reason) if blocker_reason else None,
        raw_text=raw_text,
    )
