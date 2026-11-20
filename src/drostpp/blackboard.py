"""Shared blackboard projection, deduplication, and bounded context rendering."""

from __future__ import annotations

import hashlib
import re
from typing import Iterable

from .models import BlackboardEntry, BlackboardKind, TaskStatus
from .store import SQLiteStore

_WHITESPACE_RE = re.compile(r"\s+")


def compute_fingerprint(kind: BlackboardKind | str, title: str, body: str) -> str:
    """Compute a deterministic content fingerprint for deduplicating blackboard entries."""
    norm_title = _WHITESPACE_RE.sub(" ", title.strip().lower())
    norm_body = _WHITESPACE_RE.sub(" ", body.strip().lower())[:256]
    raw = f"{str(kind).lower()}|{norm_title}|{norm_body}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class Blackboard:
    """High-level interface over durable blackboard entries stored in SQLiteStore."""

    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def publish(
        self,
        run_id: str,
        kind: BlackboardKind,
        title: str,
        body: str,
        *,
        task_id: str | None = None,
        attempt_id: str | None = None,
        generation: int | None = None,
        tags: Iterable[str] = (),
        confidence: float = 0.5,
        supersedes_id: str | None = None,
        deduplicate: bool = True,
    ) -> tuple[BlackboardEntry, bool]:
        clean_title = title.strip() or f"{kind} item"
        clean_body = body.strip()
        fp = compute_fingerprint(kind, clean_title, clean_body)
        return self.store.add_blackboard_entry(
            run_id,
            kind,
            clean_title,
            clean_body,
            fp,
            task_id=task_id,
            attempt_id=attempt_id,
            generation=generation,
            tags=[str(t).strip() for t in tags if str(t).strip()],
            confidence=max(0.0, min(1.0, float(confidence))),
            supersedes_id=supersedes_id,
            deduplicate=deduplicate,
        )

    def list_entries(
        self, run_id: str, *, kind: BlackboardKind | None = None
    ) -> list[BlackboardEntry]:
        return self.store.list_blackboard_entries(run_id, kind=kind)

    def sibling_summaries(
        self,
        run_id: str,
        *,
        exclude_task_id: str | None = None,
        limit: int = 12,
    ) -> list[str]:
        """Return concise summaries of sibling tasks and hypotheses so workers diverge."""
        lines: list[str] = []
        tasks = self.store.list_tasks(run_id)
        for task in reversed(tasks):
            if exclude_task_id and task.task_id == exclude_task_id:
                continue
            if task.status in (TaskStatus.CANCELLED,):
                continue
            lines.append(f"Task [{task.status}] {task.title}")
            if len(lines) >= limit:
                break

        if len(lines) < limit:
            hyps = self.store.list_blackboard_entries(run_id, kind=BlackboardKind.HYPOTHESIS)
            for entry in reversed(hyps):
                if exclude_task_id and entry.task_id == exclude_task_id:
                    continue
                lines.append(f"Hypothesis: {entry.title}")
                if len(lines) >= limit:
                    break
        return lines[:limit]

    def render_context(
        self,
        run_id: str,
        *,
        max_chars: int = 12_000,
        exclude_task_id: str | None = None,
    ) -> str:
        """Render a compact, strictly char-bounded blackboard digest for worker prompts."""
        if max_chars <= 0:
            return ""
        entries = self.store.list_blackboard_entries(run_id)
        if not entries:
            return "(blackboard is currently empty)"

        superseded = {e.supersedes_id for e in entries if e.supersedes_id}
        active = [
            e
            for e in entries
            if e.entry_id not in superseded
            and not (exclude_task_id and e.task_id == exclude_task_id and e.kind == BlackboardKind.NOTE)
        ]

        sections: list[tuple[str, list[BlackboardEntry]]] = [
            ("Findings", [e for e in active if e.kind == BlackboardKind.FINDING]),
            ("Facts", [e for e in active if e.kind == BlackboardKind.FACT]),
            ("Hypotheses", [e for e in active if e.kind == BlackboardKind.HYPOTHESIS]),
            ("Artifacts", [e for e in active if e.kind == BlackboardKind.ARTIFACT_REF]),
            ("Notes", [e for e in active if e.kind in (BlackboardKind.NOTE, BlackboardKind.SYNTHESIS)]),
        ]

        parts: list[str] = []
        used = 0
        trunc_notice = "\n...[blackboard context truncated to budget]"
        limit = max(0, max_chars - len(trunc_notice))

        for heading, group in sections:
            if not group:
                continue
            header = f"### {heading}\n"
            if used + len(header) > limit:
                parts.append(trunc_notice)
                break
            parts.append(header)
            used += len(header)
            for entry in reversed(group):
                snippet = _WHITESPACE_RE.sub(" ", entry.body).strip()
                if len(snippet) > 320:
                    snippet = snippet[:317] + "..."
                tag_str = f" [{', '.join(entry.tags)}]" if entry.tags else ""
                line = (
                    f"- ({entry.entry_id}, conf={entry.confidence:.2f}{tag_str}) "
                    f"**{entry.title}**: {snippet}\n"
                )
                if used + len(line) > limit:
                    parts.append(trunc_notice)
                    return "".join(parts)[:max_chars]
                parts.append(line)
                used += len(line)
        return "".join(parts)[:max_chars].strip()
