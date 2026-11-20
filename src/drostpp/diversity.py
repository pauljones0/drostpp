"""Controlled exploration diversity: least-used persona rotation, KB sampling, and sibling avoidance."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import random
from typing import Any

from .blackboard import Blackboard
from .config import DEFAULT_PERSONAS, DiversityConfig
from .models import DiversityAssignment
from .store import SQLiteStore

_MAX_DOC_BYTES = 16 * 1024


@dataclass(frozen=True, slots=True)
class KnowledgeItem:
    item_id: str
    title: str
    category: str
    summary: str
    tags: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.item_id,
            "title": self.title,
            "category": self.category,
            "summary": self.summary,
            "tags": list(self.tags),
        }


class KnowledgeBaseSampler:
    """Loads optional JSONL or file-directory strategy seeds for exploration diversity."""

    def __init__(self, source_path: Path | str | None) -> None:
        self.source_path = Path(source_path) if source_path else None
        self.items: list[KnowledgeItem] = []
        self.warnings: list[str] = []
        if self.source_path is not None:
            self._load()

    def _load(self) -> None:
        path = self.source_path
        if path is None or not path.exists():
            return
        if path.is_file():
            self._load_jsonl(path)
        elif path.is_dir():
            self._load_directory(path)

    def _load_jsonl(self, path: Path) -> None:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            self.warnings.append(f"failed to read KB file {path}: {exc}")
            return
        for idx, raw_line in enumerate(text.splitlines(), start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                self.warnings.append(f"{path}:{idx}: skipping malformed JSONL: {exc}")
                continue
            if not isinstance(obj, dict):
                continue
            title = str(obj.get("title") or obj.get("name") or f"item-{idx}").strip()
            summary = str(obj.get("summary") or obj.get("description") or obj.get("prompt") or "").strip()
            item_id = str(obj.get("id") or f"kb_{idx}_{hashlib.sha256(title.encode()).hexdigest()[:8]}")
            category = str(obj.get("category") or "general").strip()
            tags_raw = obj.get("tags") or []
            tags = tuple(str(t).strip() for t in tags_raw if str(t).strip()) if isinstance(tags_raw, list) else ()
            self.items.append(
                KnowledgeItem(
                    item_id=item_id,
                    title=title,
                    category=category,
                    summary=summary[:1500],
                    tags=tags,
                )
            )

    def _load_directory(self, root: Path) -> None:
        for file_path in sorted(root.rglob("*")):
            if not file_path.is_file() or file_path.is_symlink():
                continue
            suffix = file_path.suffix.lower()
            if suffix not in {".md", ".txt", ".json"}:
                continue
            try:
                raw = file_path.read_bytes()[:_MAX_DOC_BYTES].decode("utf-8", errors="replace").strip()
            except OSError as exc:
                self.warnings.append(f"failed to read KB doc {file_path}: {exc}")
                continue
            if not raw:
                continue
            rel = str(file_path.relative_to(root))
            if suffix == ".json":
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError:
                    obj = None
                if isinstance(obj, dict):
                    title = str(obj.get("title") or rel)
                    summary = str(obj.get("summary") or raw)[:1500]
                    category = str(obj.get("category") or "general")
                    item_id = str(obj.get("id") or rel)
                    self.items.append(KnowledgeItem(item_id=item_id, title=title, category=category, summary=summary))
                    continue
            first_line = raw.splitlines()[0].lstrip("# ").strip()
            self.items.append(
                KnowledgeItem(
                    item_id=rel,
                    title=first_line or rel,
                    category=file_path.parent.name if file_path.parent != root else "general",
                    summary=raw[:1500],
                )
            )


class DiversityEngine:
    """Assigns distinct deterministic exploration perspectives and KB seeds across tasks."""

    def __init__(self, config: DiversityConfig) -> None:
        self.config = config
        self.personas = list(config.personas) if config.personas else [dict(p) for p in DEFAULT_PERSONAS]
        self.kb = KnowledgeBaseSampler(config.knowledge_base_path)

    def assign_for_attempt(
        self,
        store: SQLiteStore,
        run_id: str,
        run_seed: int,
        task_id: str,
        generation: int,
    ) -> DiversityAssignment:
        seed_material = f"{run_seed}:{task_id}:{generation}".encode("utf-8")
        angle_seed = int.from_bytes(hashlib.sha256(seed_material).digest()[:8], "big") & 0x7FFF_FFFF_FFFF_FFFF
        rng = random.Random(angle_seed)

        if not self.config.enabled:
            first = self.personas[0]
            assignment = store.record_diversity_assignment(
                run_id, task_id, generation, first["name"], [], angle_seed
            )
            assignment.instructions = first["instructions"]
            return assignment

        prior = store.list_diversity_assignments(run_id)
        persona_counts: dict[str, int] = {p["name"]: 0 for p in self.personas}
        kb_counts: dict[str, int] = {item.item_id: 0 for item in self.kb.items}

        for prev in prior:
            if prev.persona in persona_counts:
                persona_counts[prev.persona] += 1
            for item_id in prev.kb_item_ids:
                if item_id in kb_counts:
                    kb_counts[item_id] += 1

        min_persona_count = min(persona_counts.values())
        least_used_personas = [p for p in self.personas if persona_counts[p["name"]] == min_persona_count]
        chosen_persona = rng.choice(least_used_personas)

        chosen_kb: list[KnowledgeItem] = []
        if self.kb.items and self.config.kb_samples_per_task > 0:
            # Sort by usage count ascending, breaking ties with seeded randomness.
            shuffled = list(self.kb.items)
            rng.shuffle(shuffled)
            shuffled.sort(key=lambda item: kb_counts[item.item_id])
            chosen_kb = shuffled[: self.config.kb_samples_per_task]

        assignment = store.record_diversity_assignment(
            run_id,
            task_id,
            generation,
            chosen_persona["name"],
            [item.item_id for item in chosen_kb],
            angle_seed,
        )
        assignment.instructions = chosen_persona["instructions"]
        assignment.kb_items = [item.to_dict() for item in chosen_kb]
        return assignment

    def render_framing(
        self,
        assignment: DiversityAssignment,
        blackboard: Blackboard,
        *,
        run_id: str,
        task_id: str,
    ) -> str:
        lines: list[str] = [
            f"Exploration Persona: `{assignment.persona}` (angle_seed={assignment.angle_seed})",
        ]
        if assignment.instructions:
            lines.append(f"Guidance: {assignment.instructions}")
        if assignment.kb_items:
            lines.append("Seeded Exploration Angles (use as inspiration, validate everything):")
            for item in assignment.kb_items:
                summary = str(item.get("summary", "")).strip()
                if len(summary) > 300:
                    summary = summary[:297] + "..."
                lines.append(f"- [{item.get('category', 'general')}] {item.get('title')}: {summary}")
        if self.config.include_sibling_avoidance:
            siblings = blackboard.sibling_summaries(run_id, exclude_task_id=task_id, limit=10)
            if siblings:
                lines.append(
                    "Already Explored by Siblings (avoid repeating these same steps; probe a different angle):"
                )
                for sib in siblings:
                    lines.append(f"- {sib}")
        return "\n".join(lines)
