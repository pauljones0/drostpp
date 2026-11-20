"""Headless CLI (`drost++` / `drostpp`) for running, resuming, inspecting, and syncing orchestrated runs."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import shutil
import sys
from typing import Any

from .config import OrchestratorConfig, config_to_toml, load_config
from .coordinator import Coordinator
from .integrations.drost import DrostWorkspaceBridge, check_drost_health
from .models import BlackboardKind, RunPhase, TaskKind
from .store import SQLiteStore


def _print_json(data: Any) -> None:
    print(json.dumps(data, indent=2, sort_keys=True, default=str))


def _resolve_run_id(store: SQLiteStore, run_id: str | None) -> str:
    if run_id:
        return run_id
    runs = store.list_runs()
    if not runs:
        raise SystemExit("no runs found in state directory")
    return runs[0].run_id


def _cmd_init(args: argparse.Namespace) -> int:
    target_dir = Path(args.dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "state").mkdir(exist_ok=True)

    cfg = OrchestratorConfig()
    if args.kb:
        cfg.diversity.knowledge_base_path = str(Path(args.kb).expanduser())
    if args.with_drost:
        cfg.drost.enabled = True
        cfg.drost.container_name = args.drost_container
        cfg.drost.mcp_mode = args.drost_mode
        if args.drost_workspace:
            cfg.drost.workspace_host_path = str(Path(args.drost_workspace).expanduser())

    cfg_path = target_dir / "config.toml"
    cfg_path.write_text(config_to_toml(cfg), encoding="utf-8")
    _print_json(
        {
            "initialized": str(target_dir),
            "config_path": str(cfg_path),
            "state_dir": str(target_dir / "state"),
            "drost_enabled": cfg.drost.enabled,
        }
    )
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    if args.workers is not None:
        cfg.run.max_workers = max(1, int(args.workers))
    if args.seed is not None:
        cfg.run.seed = int(args.seed)
    if args.no_verify:
        cfg.run.enable_verify_phase = False
    if args.drost_engagement:
        cfg.drost.enabled = True
        cfg.drost.engagement_id = args.drost_engagement

    state_dir = Path(args.state_dir).resolve()
    workspace_dir = Path(args.workspace).resolve() if args.workspace else state_dir
    coord = Coordinator(
        state_dir,
        cfg,
        workspace_dir=workspace_dir,
        use_mock=args.mock,
    )
    try:
        run_rec = coord.run(
            args.goal,
            seed=args.seed,
            drost_engagement_id=args.drost_engagement,
        )
        tasks = coord.store.list_tasks(run_rec.run_id)
        bb = coord.blackboard.list_entries(run_rec.run_id)
        _print_json(
            {
                "run_id": run_rec.run_id,
                "phase": run_rec.phase,
                "plan_materialized": run_rec.plan_materialized,
                "seed": run_rec.seed,
                "tokens_used": run_rec.tokens_used,
                "tasks_total": len(tasks),
                "blackboard_entries": len(bb),
                "error_message": run_rec.error_message,
            }
        )
        return 0 if run_rec.phase == RunPhase.COMPLETED else 1
    finally:
        coord.close()


def _cmd_resume(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    state_dir = Path(args.state_dir).resolve()
    coord = Coordinator(state_dir, cfg, use_mock=args.mock)
    try:
        run_id = _resolve_run_id(coord.store, args.run_id)
        run_rec = coord.resume(run_id)
        _print_json(
            {
                "run_id": run_rec.run_id,
                "phase": run_rec.phase,
                "tokens_used": run_rec.tokens_used,
                "error_message": run_rec.error_message,
            }
        )
        return 0 if run_rec.phase == RunPhase.COMPLETED else 1
    finally:
        coord.close()


def _cmd_status(args: argparse.Namespace) -> int:
    store = SQLiteStore(Path(args.state_dir).resolve() / "drostpp.db")
    try:
        run_id = _resolve_run_id(store, args.run_id)
        run_rec = store.get_run(run_id)
        if run_rec is None:
            raise SystemExit(f"unknown run_id: {run_id}")
        tasks = store.list_tasks(run_id)
        attempts = store.list_attempts(run_id)
        bb = store.list_blackboard_entries(run_id)
        artifacts = store.list_artifacts(run_id)
        payload = {
            "run": asdict(run_rec),
            "task_counts": {
                status: sum(1 for t in tasks if t.status == status)
                for status in sorted({t.status for t in tasks})
            },
            "tasks": [
                {
                    "task_id": t.task_id,
                    "title": t.title,
                    "kind": t.kind,
                    "status": t.status,
                    "generation": t.generation,
                    "retry_count": t.retry_count,
                }
                for t in tasks
            ],
            "attempts_total": len(attempts),
            "blackboard_entries": len(bb),
            "artifacts": len(artifacts),
        }
        if args.json:
            _print_json(payload)
        else:
            print(
                f"Run {run_rec.run_id} | phase={run_rec.phase} | "
                f"plan_materialized={run_rec.plan_materialized} | tokens={run_rec.tokens_used} | "
                f"tasks={len(tasks)} | blackboard={len(bb)} | artifacts={len(artifacts)}"
            )
            for t in tasks:
                print(f"  - [{t.status}] {t.task_id} ({t.kind}/gen={t.generation}): {t.title}")
        return 0
    finally:
        store.close()


def _cmd_phase_op(args: argparse.Namespace, target: RunPhase) -> int:
    store = SQLiteStore(Path(args.state_dir).resolve() / "drostpp.db")
    try:
        run_id = _resolve_run_id(store, args.run_id)
        updated = store.transition_run_phase(
            run_id, target, actor="operator", reason=f"cli {target}"
        )
        _print_json({"run_id": updated.run_id, "phase": updated.phase})
        return 0
    finally:
        store.close()


def _cmd_task(args: argparse.Namespace) -> int:
    store = SQLiteStore(Path(args.state_dir).resolve() / "drostpp.db")
    try:
        if args.task_cmd == "add":
            run_id = _resolve_run_id(store, args.run_id)
            task = store.add_task(
                run_id,
                args.title,
                args.prompt,
                kind=TaskKind(args.kind),
                role=args.role,
                tier=args.tier,
                priority=args.priority,
                depends_on=args.depends_on or [],
                actor="operator",
            )
            _print_json(asdict(task))
        elif args.task_cmd == "list":
            run_id = _resolve_run_id(store, args.run_id)
            _print_json([asdict(t) for t in store.list_tasks(run_id)])
        elif args.task_cmd == "pause":
            _print_json(asdict(store.pause_task(args.task_id)))
        elif args.task_cmd == "resume":
            _print_json(asdict(store.resume_task(args.task_id)))
        return 0
    finally:
        store.close()


def _cmd_blackboard(args: argparse.Namespace) -> int:
    store = SQLiteStore(Path(args.state_dir).resolve() / "drostpp.db")
    from .blackboard import Blackboard

    bb = Blackboard(store)
    try:
        run_id = _resolve_run_id(store, args.run_id)
        if args.bb_cmd == "list":
            kind = BlackboardKind(args.kind) if args.kind else None
            _print_json([asdict(e) for e in bb.list_entries(run_id, kind=kind)])
        elif args.bb_cmd == "add":
            entry, dedup = bb.publish(
                run_id,
                BlackboardKind(args.kind),
                args.title,
                args.body,
                tags=args.tag or [],
                confidence=args.confidence,
            )
            _print_json({"entry": asdict(entry), "deduplicated": dedup})
        return 0
    finally:
        store.close()


def _cmd_events(args: argparse.Namespace) -> int:
    store = SQLiteStore(Path(args.state_dir).resolve() / "drostpp.db")
    try:
        run_id = _resolve_run_id(store, args.run_id)
        _print_json(store.list_events(run_id, after_seq=args.after))
        return 0
    finally:
        store.close()


def _cmd_drost(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    if args.drost_cmd == "check":
        if args.container:
            cfg.drost.container_name = args.container
        res = check_drost_health(cfg.drost)
        _print_json(res)
        return 0 if res.get("healthy") else 1

    ws_path = args.workspace or cfg.drost.workspace_host_path
    if not ws_path:
        raise SystemExit("provide --workspace or set drost.workspace_host_path in config")
    bridge = DrostWorkspaceBridge(ws_path)
    if args.drost_cmd == "list-engagements":
        _print_json(bridge.list_engagements())
        return 0
    if args.drost_cmd == "sync":
        state_dir = Path(args.state_dir).resolve()
        store = SQLiteStore(state_dir / "drostpp.db")
        from .blackboard import Blackboard

        bb = Blackboard(store)
        try:
            run_id = _resolve_run_id(store, args.run_id)
            eng_id = args.engagement_id or cfg.drost.engagement_id
            if not eng_id:
                raise SystemExit("provide --engagement-id or set drost.engagement_id")
            res = bridge.sync_engagement_to_run(
                store,
                bb,
                run_id=run_id,
                engagement_id=eng_id,
                artifact_store_dir=state_dir / "runs" / run_id / "artifacts",
                max_import_bytes=cfg.drost.max_import_bytes,
            )
            _print_json(res)
            return 0
        finally:
            store.close()
    return 1


def _cmd_doctor(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    codex_bin = shutil.which(cfg.codex.binary)
    kimi_bin = shutil.which(cfg.kimi.cli_binary)
    docker_bin = shutil.which(cfg.drost.docker_binary)
    codex_home = Path(cfg.codex.codex_home or os.environ.get("CODEX_HOME", "~/.codex")).expanduser()
    codex_auth_present = (codex_home / "auth.json").is_file()
    kimi_key_present = bool(
        os.environ.get(cfg.kimi.api_key_env) or os.environ.get("MOONSHOT_API_KEY")
    )
    report: dict[str, Any] = {
        "python_version": sys.version.split()[0],
        "codex": {
            "binary": codex_bin,
            "codex_home": str(codex_home),
            "auth_json_present": codex_auth_present,
        },
        "kimi": {
            "mode": cfg.kimi.mode,
            "api_key_env": cfg.kimi.api_key_env,
            "api_key_configured": kimi_key_present,
            "cli_binary": kimi_bin,
        },
        "docker_binary": docker_bin,
        "drost": {
            "enabled": cfg.drost.enabled,
            "container_name": cfg.drost.container_name,
            "mcp_mode": cfg.drost.mcp_mode,
            "workspace_host_path": cfg.drost.workspace_host_path,
        },
    }
    _print_json(report)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="drost++", description="drost++ durable multi-agent orchestration CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="Initialize a drost++ directory and config.toml")
    p_init.add_argument("dir")
    p_init.add_argument("--with-drost", action="store_true")
    p_init.add_argument("--drost-container", default="drost-ai")
    p_init.add_argument("--drost-workspace", default=None)
    p_init.add_argument("--drost-mode", choices=["compact", "full"], default="compact")
    p_init.add_argument("--kb", default=None, help="Path to diversity knowledge base JSONL or dir")

    p_run = sub.add_parser("run", help="Create and execute a new orchestrated run")
    p_run.add_argument("--config", default=None)
    p_run.add_argument("--goal", required=True)
    p_run.add_argument("--state-dir", default=".drostpp_state")
    p_run.add_argument("--workspace", default=None)
    p_run.add_argument("--seed", type=int, default=None)
    p_run.add_argument("--workers", type=int, default=None)
    p_run.add_argument("--drost-engagement", default=None)
    p_run.add_argument("--no-verify", action="store_true")
    p_run.add_argument("--mock", action="store_true")

    p_res = sub.add_parser("resume", help="Recover and resume an interrupted or paused run")
    p_res.add_argument("--state-dir", default=".drostpp_state")
    p_res.add_argument("--run-id", default=None)
    p_res.add_argument("--config", default=None)
    p_res.add_argument("--mock", action="store_true")

    p_stat = sub.add_parser("status", help="Show run phase, tasks, blackboard, and artifact counts")
    p_stat.add_argument("--state-dir", default=".drostpp_state")
    p_stat.add_argument("--run-id", default=None)
    p_stat.add_argument("--json", action="store_true")

    p_pause = sub.add_parser("pause", help="Mark a run as paused")
    p_pause.add_argument("--state-dir", default=".drostpp_state")
    p_pause.add_argument("--run-id", default=None)

    p_cancel = sub.add_parser("cancel", help="Cancel a run")
    p_cancel.add_argument("--state-dir", default=".drostpp_state")
    p_cancel.add_argument("--run-id", default=None)

    p_task = sub.add_parser("task", help="Manage tasks in a run")
    p_task_sub = p_task.add_subparsers(dest="task_cmd", required=True)
    pt_add = p_task_sub.add_parser("add")
    pt_add.add_argument("--state-dir", default=".drostpp_state")
    pt_add.add_argument("--run-id", default=None)
    pt_add.add_argument("--title", required=True)
    pt_add.add_argument("--prompt", required=True)
    pt_add.add_argument("--kind", choices=["plan", "work", "verify", "synthesize"], default="work")
    pt_add.add_argument("--role", default="worker")
    pt_add.add_argument("--tier", default="default")
    pt_add.add_argument("--priority", type=int, default=0)
    pt_add.add_argument("--depends-on", action="append", default=[])

    pt_list = p_task_sub.add_parser("list")
    pt_list.add_argument("--state-dir", default=".drostpp_state")
    pt_list.add_argument("--run-id", default=None)

    pt_pause = p_task_sub.add_parser("pause")
    pt_pause.add_argument("--state-dir", default=".drostpp_state")
    pt_pause.add_argument("--task-id", required=True)

    pt_resume = p_task_sub.add_parser("resume")
    pt_resume.add_argument("--state-dir", default=".drostpp_state")
    pt_resume.add_argument("--task-id", required=True)

    p_bb = sub.add_parser("blackboard", help="Inspect or publish blackboard entries")
    p_bb_sub = p_bb.add_subparsers(dest="bb_cmd", required=True)
    pb_list = p_bb_sub.add_parser("list")
    pb_list.add_argument("--state-dir", default=".drostpp_state")
    pb_list.add_argument("--run-id", default=None)
    pb_list.add_argument("--kind", default=None)

    pb_add = p_bb_sub.add_parser("add")
    pb_add.add_argument("--state-dir", default=".drostpp_state")
    pb_add.add_argument("--run-id", default=None)
    pb_add.add_argument(
        "--kind",
        choices=["fact", "hypothesis", "finding", "note", "synthesis", "artifact_ref"],
        default="note",
    )
    pb_add.add_argument("--title", required=True)
    pb_add.add_argument("--body", required=True)
    pb_add.add_argument("--tag", action="append", default=[])
    pb_add.add_argument("--confidence", type=float, default=0.7)

    p_ev = sub.add_parser("events", help="Dump append-only event journal for a run")
    p_ev.add_argument("--state-dir", default=".drostpp_state")
    p_ev.add_argument("--run-id", default=None)
    p_ev.add_argument("--after", type=int, default=0)

    p_drost = sub.add_parser("drost", help="Drost health check, engagement listing, and artifact sync")
    p_drost_sub = p_drost.add_subparsers(dest="drost_cmd", required=True)
    pd_check = p_drost_sub.add_parser("check")
    pd_check.add_argument("--config", default=None)
    pd_check.add_argument("--container", default=None)

    pd_list = p_drost_sub.add_parser("list-engagements")
    pd_list.add_argument("--config", default=None)
    pd_list.add_argument("--workspace", default=None)

    pd_sync = p_drost_sub.add_parser("sync")
    pd_sync.add_argument("--config", default=None)
    pd_sync.add_argument("--state-dir", default=".drostpp_state")
    pd_sync.add_argument("--run-id", default=None)
    pd_sync.add_argument("--workspace", default=None)
    pd_sync.add_argument("--engagement-id", default=None)

    p_doc = sub.add_parser("doctor", help="Check local Python, Codex OAuth, Kimi, Docker, and Drost setup")
    p_doc.add_argument("--config", default=None)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "init":
        return _cmd_init(args)
    if args.cmd == "run":
        return _cmd_run(args)
    if args.cmd == "resume":
        return _cmd_resume(args)
    if args.cmd == "status":
        return _cmd_status(args)
    if args.cmd == "pause":
        return _cmd_phase_op(args, RunPhase.PAUSED)
    if args.cmd == "cancel":
        return _cmd_phase_op(args, RunPhase.CANCELLED)
    if args.cmd == "task":
        return _cmd_task(args)
    if args.cmd == "blackboard":
        return _cmd_blackboard(args)
    if args.cmd == "events":
        return _cmd_events(args)
    if args.cmd == "drost":
        return _cmd_drost(args)
    if args.cmd == "doctor":
        return _cmd_doctor(args)
    return 1
