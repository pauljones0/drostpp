"""Tests for Blackboard deduplication, context budget caps, and DiversityEngine rotation."""

from __future__ import annotations

import json
from pathlib import Path

from drostpp.blackboard import Blackboard
from drostpp.config import DiversityConfig
from drostpp.diversity import DiversityEngine, KnowledgeBaseSampler
from drostpp.models import BlackboardKind, RunPhase
from drostpp.store import SQLiteStore


def test_blackboard_deduplication_and_bounded_render(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "orchestrator.db")
    bb = Blackboard(store)
    try:
        run = store.create_run("bb test")
        e1, dedup1 = bb.publish(
            run.run_id,
            BlackboardKind.FACT,
            "SQLite WAL Mode",
            "   Uses write-ahead logging   with synchronous FULL.  ",
            tags=["storage"],
            confidence=0.9,
        )
        e2, dedup2 = bb.publish(
            run.run_id,
            BlackboardKind.FACT,
            "sqlite wal mode",
            "Uses write-ahead logging with synchronous FULL.",
            tags=["storage"],
        )
        assert not dedup1
        assert dedup2
        assert e1.entry_id == e2.entry_id

        for idx in range(25):
            bb.publish(
                run.run_id,
                BlackboardKind.FINDING,
                f"Finding #{idx}",
                "Detailed observation payload " * 15,
                confidence=0.8,
            )

        rendered = bb.render_context(run.run_id, max_chars=900)
        assert len(rendered) <= 900
        assert "Findings" in rendered
    finally:
        store.close()


def test_diversity_rotates_personas_and_kb_across_tasks_jsonl_and_dir(tmp_path: Path) -> None:
    kb_jsonl = tmp_path / "kb.jsonl"
    items = [
        {"id": f"kb-{i}", "title": f"Angle {i}", "category": "cat", "summary": f"Probe angle {i}"}
        for i in range(6)
    ]
    kb_jsonl.write_text("\n".join(json.dumps(x) for x in items) + "\nmalformed-line\n", encoding="utf-8")

    kb_dir = tmp_path / "kb_dir"
    kb_dir.mkdir()
    for i in range(4):
        (kb_dir / f"guide_{i}.md").write_text(f"# Dir Angle {i}\nDetails {i}", encoding="utf-8")

    sampler_dir = KnowledgeBaseSampler(kb_dir)
    assert len(sampler_dir.items) == 4

    store = SQLiteStore(tmp_path / "orchestrator.db")
    try:
        run = store.create_run("diversity test", seed=12345)
        store.transition_run_phase(run.run_id, RunPhase.PLANNING)
        store.mark_plan_materialized(run.run_id)
        store.transition_run_phase(run.run_id, RunPhase.RUNNING)

        div_cfg = DiversityConfig(
            enabled=True,
            knowledge_base_path=str(kb_jsonl),
            kb_samples_per_task=2,
            include_sibling_avoidance=True,
        )
        engine = DiversityEngine(div_cfg)
        assert len(engine.kb.warnings) == 1  # malformed line skipped cleanly

        chosen_personas: list[str] = []
        chosen_kb_ids: list[str] = []
        for idx in range(3):
            t = store.add_task(run.run_id, f"Sibling {idx}", "explore")
            a = engine.assign_for_attempt(store, run.run_id, run.seed, t.task_id, 1)
            chosen_personas.append(a.persona)
            chosen_kb_ids.extend(a.kb_item_ids)

        # 3 tasks must get 3 distinct personas and 6 distinct KB items without replacement.
        assert len(set(chosen_personas)) == 3
        assert len(chosen_kb_ids) == 6
        assert len(set(chosen_kb_ids)) == 6

        # Framing includes sibling avoidance.
        bb = Blackboard(store)
        last_task = store.list_tasks(run.run_id)[-1]
        last_assign = store.list_diversity_assignments(run.run_id)[-1]
        framing = engine.render_framing(last_assign, bb, run_id=run.run_id, task_id=last_task.task_id)
        assert "Sibling 0" in framing
        assert "Exploration Persona" in framing
    finally:
        store.close()


def test_different_seeds_vary_initial_selection_and_same_seed_reproduces(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "orchestrator.db")
    try:
        engine = DiversityEngine(DiversityConfig(enabled=True))
        r1 = store.create_run("s1", seed=42)
        t1 = store.add_task(r1.run_id, "Same Title", "same", task_id="tsk_fixed_seed_check")
        a1 = engine.assign_for_attempt(store, r1.run_id, 42, t1.task_id, 1)

        store2 = SQLiteStore(tmp_path / "orchestrator2.db")
        try:
            r2 = store2.create_run("s1", seed=42)
            t2 = store2.add_task(r2.run_id, "Same Title", "same", task_id="tsk_fixed_seed_check")
            a2 = engine.assign_for_attempt(store2, r2.run_id, 42, t2.task_id, 1)
            assert a1.persona == a2.persona
            assert a1.angle_seed == a2.angle_seed
        finally:
            store2.close()

        # Different seeds produce different angle seeds and across pool can pick different personas.
        observed_personas = set()
        for seed in range(1, 25):
            s_tmp = SQLiteStore(tmp_path / f"seed_{seed}.db")
            try:
                rx = s_tmp.create_run("sx", seed=seed)
                tx = s_tmp.add_task(rx.run_id, "T", "p", task_id="tsk_same")
                ax = engine.assign_for_attempt(s_tmp, rx.run_id, seed, tx.task_id, 1)
                observed_personas.add(ax.persona)
            finally:
                s_tmp.close()
        assert len(observed_personas) > 1
    finally:
        store.close()
