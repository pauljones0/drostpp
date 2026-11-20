"""Durable run coordinator: explicit phase machine, fenced execution, recovery, and diversity."""

from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
import json
import os
from pathlib import Path
import signal
import sys
import threading
from typing import Any

from .adapters.base import AttemptContext, WORKER_OUTPUT_JSON_SCHEMA, WorkerAdapter
from .adapters.codex import CodexAdapter
from .adapters.kimi import KimiApiAdapter, KimiCliAdapter
from .adapters.mock import MockAdapter
from .blackboard import Blackboard
from .budgets import BudgetTracker, compute_dir_bytes, error_signature
from .config import OrchestratorConfig
from .diversity import DiversityEngine
from .integrations.drost import DrostWorkspaceBridge, build_drost_mcp_config
from .models import (
    AttemptRecord,
    AttemptResult,
    BlackboardKind,
    BudgetExceededError,
    ErrorKind,
    FencedAttemptError,
    FollowUpProposal,
    IllegalTransitionError,
    McpServerConfig,
    ManagedResource,
    RunPhase,
    RunRecord,
    TaskBudget,
    TaskKind,
    TaskRecord,
    TaskStatus,
    WorkerOutput,
)
from .routing import ModelRouter
from .resources import ResourceManager
from .store import CoordinatorLock, SQLiteStore
from .supervision import DockerRunner, ProcessSupervisor, terminate_process_group


class Coordinator:
    """Single-process coordinator owning run lifecycle, leases, worker pools, and state transitions."""

    def __init__(
        self,
        state_dir: Path | str,
        config: OrchestratorConfig | None = None,
        *,
        workspace_dir: Path | str | None = None,
        adapters: dict[str, WorkerAdapter] | None = None,
        use_mock: bool = False,
    ) -> None:
        self.state_dir = Path(state_dir).resolve()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.workspace_dir = Path(workspace_dir).resolve() if workspace_dir else self.state_dir
        self.config = config or OrchestratorConfig()
        self.store = SQLiteStore(self.state_dir / "drostpp.db")
        self.blackboard = Blackboard(self.store)
        self.diversity = DiversityEngine(self.config.diversity)
        self.router = ModelRouter(self.config.routing)
        self.supervisor = ProcessSupervisor()
        self.docker = DockerRunner(self.config.container.docker_binary)
        self.budget_tracker = BudgetTracker(self.config.budgets.to_run_budget())
        self.budget_tracker.set_host_memory_floor(
            self.config.budgets.min_available_memory_mb
        )
        self.resources = ResourceManager(
            self.store,
            self.config.container,
            docker=self.docker,
            attempt_lease_seconds=self.config.run.lease_seconds,
            min_available_memory_mb=self.config.budgets.min_available_memory_mb,
            min_free_disk_bytes=self.config.budgets.min_free_disk_bytes,
        )
        self._shutdown_event = threading.Event()

        if adapters is not None:
            self.adapters: dict[str, WorkerAdapter] = dict(adapters)
        elif use_mock:
            mock = MockAdapter()
            self.adapters = {"codex": mock, "kimi": mock, "mock": mock}
        else:
            kimi_adapter: WorkerAdapter = (
                KimiApiAdapter(self.config.kimi)
                if self.config.kimi.mode == "api"
                else KimiCliAdapter(
                    self.config.kimi,
                    supervisor=self.supervisor,
                    heartbeat_interval=self.config.run.heartbeat_seconds,
                )
            )
            self.adapters = {
                "codex": CodexAdapter(
                    self.config.codex,
                    supervisor=self.supervisor,
                    heartbeat_interval=self.config.run.heartbeat_seconds,
                ),
                "kimi": kimi_adapter,
                "mock": MockAdapter(),
            }

    def close(self) -> None:
        self.store.close()

    def request_shutdown(self) -> None:
        self._shutdown_event.set()

    def acquire_lock(self) -> CoordinatorLock:
        return CoordinatorLock(self.state_dir / "coordinator.lock", self.store.db_path)

    def _active_mcp_servers(
        self, run_id: str, task_id: str, attempt_id: str, generation: int
    ) -> list[McpServerConfig]:
        servers = [srv for srv in self.config.mcp_servers.values() if srv.enabled]
        if self.config.drost.enabled:
            drost_server = build_drost_mcp_config(self.config.drost)
            if self.config.container.enabled and self.config.container.block_direct_docker:
                drost_server.args = [
                    "-m",
                    "drostpp.docker_passthrough",
                    drost_server.command,
                    *drost_server.args,
                ]
                drost_server.command = sys.executable
            servers.append(drost_server)
        if self.config.container.enabled:
            servers = [srv for srv in servers if srv.name != "drostpp_resources"]
            servers.append(
                McpServerConfig(
                    name="drostpp_resources",
                    command=sys.executable,
                    args=["-m", "drostpp.resource_mcp"],
                    env={
                        "DROSTPP_STATE_DIR": str(self.state_dir),
                        "DROSTPP_RUN_ID": run_id,
                        "DROSTPP_TASK_ID": task_id,
                        "DROSTPP_ATTEMPT_ID": attempt_id,
                        "DROSTPP_GENERATION": str(generation),
                    },
                    timeout_seconds=max(300.0, self.config.run.lease_seconds),
                    max_result_bytes=self.config.budgets.max_output_bytes,
                )
            )
        return servers

    def create_run(
        self,
        goal: str,
        *,
        seed: int | None = None,
        drost_engagement_id: str | None = None,
    ) -> RunRecord:
        eff_seed = seed if seed is not None else self.config.run.seed
        eff_eng = drost_engagement_id or self.config.drost.engagement_id
        return self.store.create_run(
            goal,
            seed=eff_seed,
            config=self.config.to_public_dict(),
            budget=self.config.budgets.to_run_budget(),
            drost_engagement_id=eff_eng,
        )

    def recover(self, run_id: str) -> list[AttemptRecord]:
        """Reconcile interrupted attempts/tasks and kill any lingering OS process groups or containers."""
        stale = self.store.recover_run(run_id)
        for att in stale:
            if att.pgid:
                terminate_process_group(att.pgid, grace_seconds=0.5, hard_wait_seconds=1.5)
            if att.container_id:
                self.docker.force_remove_container(att.container_id)
            self.resources.release_attempt(att.attempt_id)
        self.resources.reap(run_id)
        return stale

    def _sync_drost_if_configured(self, run: RunRecord) -> None:
        if not (
            self.config.drost.enabled
            and self.config.drost.workspace_host_path
            and run.drost_engagement_id
        ):
            return
        bridge = DrostWorkspaceBridge(self.config.drost.workspace_host_path)
        artifact_dir = self.state_dir / "runs" / run.run_id / "artifacts"
        try:
            bridge.sync_engagement_to_run(
                self.store,
                self.blackboard,
                run_id=run.run_id,
                engagement_id=run.drost_engagement_id,
                artifact_store_dir=artifact_dir,
                max_import_bytes=self.config.drost.max_import_bytes,
            )
        except Exception as exc:
            self.blackboard.publish(
                run.run_id,
                BlackboardKind.NOTE,
                "Drost workspace sync warning",
                f"Skipped/partial Drost sync for {run.drost_engagement_id}: {exc}",
                tags=["drost", "warning"],
                confidence=0.4,
            )

    def run(
        self,
        goal: str,
        *,
        seed: int | None = None,
        drost_engagement_id: str | None = None,
    ) -> RunRecord:
        with self.acquire_lock():
            run_rec = self.create_run(
                goal, seed=seed, drost_engagement_id=drost_engagement_id
            )
            return self._drive_run(run_rec.run_id)

    def resume(self, run_id: str) -> RunRecord:
        with self.acquire_lock():
            run_rec = self.store.get_run(run_id)
            if run_rec is None:
                raise ValueError(f"unknown run_id: {run_id}")
            self.recover(run_id)
            run_rec = self.store.get_run(run_id)
            assert run_rec is not None
            if run_rec.phase == RunPhase.PAUSED:
                target_phase = (
                    RunPhase.RUNNING if run_rec.plan_materialized else RunPhase.PLANNING
                )
                self.store.transition_run_phase(
                    run_id, target_phase, actor="coordinator", reason="resumed"
                )
            return self._drive_run(run_id)

    def _drive_run(self, run_id: str) -> RunRecord:
        self._shutdown_event.clear()
        old_handlers = self._install_signal_handlers()
        try:
            run_rec = self.store.get_run(run_id)
            assert run_rec is not None

            if run_rec.phase in (
                RunPhase.COMPLETED,
                RunPhase.FAILED,
                RunPhase.CANCELLED,
            ):
                self.resources.close_run(run_id)
                return run_rec

            self._sync_drost_if_configured(run_rec)

            while not self._shutdown_event.is_set():
                run_rec = self.store.get_run(run_id)
                assert run_rec is not None
                self.resources.reap(run_id)

                if run_rec.phase == RunPhase.INIT:
                    self._handle_init(run_rec)
                elif run_rec.phase == RunPhase.PLANNING:
                    self._handle_planning(run_rec)
                elif run_rec.phase == RunPhase.RUNNING:
                    self._handle_running(run_rec)
                elif run_rec.phase == RunPhase.VERIFYING:
                    self._handle_verifying(run_rec)
                else:
                    break

            final = self.store.get_run(run_id)
            assert final is not None
            if self._shutdown_event.is_set() and final.phase in (
                RunPhase.INIT,
                RunPhase.PLANNING,
                RunPhase.RUNNING,
                RunPhase.VERIFYING,
            ):
                self.store.transition_run_phase(
                    run_id,
                    RunPhase.PAUSED,
                    actor="coordinator",
                    reason="shutdown requested",
                )
                final = self.store.get_run(run_id)
                assert final is not None
            if final.phase in (
                RunPhase.PAUSED,
                RunPhase.COMPLETED,
                RunPhase.FAILED,
                RunPhase.CANCELLED,
            ):
                self.resources.close_run(run_id)
            return final
        finally:
            self._restore_signal_handlers(old_handlers)

    def _install_signal_handlers(self) -> dict[int, Any]:
        if threading.current_thread() is not threading.main_thread():
            return {}
        saved: dict[int, Any] = {}
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                saved[sig] = signal.getsignal(sig)
                signal.signal(sig, lambda _s, _f: self._shutdown_event.set())
            except (ValueError, OSError):
                pass
        return saved

    def _restore_signal_handlers(self, saved: dict[int, Any]) -> None:
        if not saved or threading.current_thread() is not threading.main_thread():
            return
        for sig, handler in saved.items():
            try:
                signal.signal(sig, handler)
            except (ValueError, OSError):
                pass

    def _handle_init(self, run_rec: RunRecord) -> None:
        existing_tasks = self.store.list_tasks(run_rec.run_id)
        if existing_tasks:
            self.store.transition_run_phase(
                run_rec.run_id,
                RunPhase.PLANNING,
                actor="coordinator",
                reason="tasks pre-seeded",
            )
            self.store.mark_plan_materialized(run_rec.run_id)
            self.store.transition_run_phase(
                run_rec.run_id,
                RunPhase.RUNNING,
                actor="coordinator",
                reason="entering running with pre-seeded plan",
            )
            return
        self.store.transition_run_phase(
            run_rec.run_id,
            RunPhase.PLANNING,
            actor="coordinator",
            reason="begin planning",
        )

    def _handle_planning(self, run_rec: RunRecord) -> None:
        if run_rec.plan_materialized:
            self.store.transition_run_phase(
                run_rec.run_id,
                RunPhase.RUNNING,
                actor="coordinator",
                reason="plan already materialized",
            )
            return

        try:
            disk_bytes = self.budget_tracker.check_run_admission(
                run_rec,
                self.state_dir,
                reserve_memory_mb=self.config.budgets.default_task_memory_mb,
            )
            self.store.update_run_disk_bytes(run_rec.run_id, disk_bytes)
        except BudgetExceededError as exc:
            self.store.transition_run_phase(
                run_rec.run_id,
                RunPhase.FAILED,
                actor="coordinator",
                error_message=str(exc),
            )
            return

        tasks = self.store.list_tasks(run_rec.run_id)
        plan_tasks = [t for t in tasks if t.kind == TaskKind.PLAN]
        if not plan_tasks:
            self.store.add_task(
                run_rec.run_id,
                "Decompose goal into bounded tasks",
                (
                    f"Create a clear, bounded work plan for this goal:\n{run_rec.goal}\n\n"
                    "Return structured follow_up_tasks that explore complementary angles in parallel "
                    "where appropriate, using depends_on_titles only where ordering is required."
                ),
                kind=TaskKind.PLAN,
                role="planner",
                tier="strong",
                priority=100,
                budget=self.config.budgets.to_task_budget(),
            )
        elif all(t.status == TaskStatus.FAILED for t in plan_tasks):
            self.store.transition_run_phase(
                run_rec.run_id,
                RunPhase.FAILED,
                actor="coordinator",
                error_message="planning task failed permanently",
            )
            return

        claimed = self.store.claim_next_task(
            run_rec.run_id,
            "planner-0",
            "pending",
            "",
            lease_seconds=self.config.run.lease_seconds,
            kinds=(TaskKind.PLAN,),
            route_resolver=self._route_pair,
        )
        if claimed is None:
            return

        task, attempt = claimed
        cancel_ev = threading.Event()
        self._execute_claimed_task(run_rec, task, attempt, cancel_ev)

        refreshed_task = self.store.get_task(task.task_id)
        assert refreshed_task is not None
        if self._shutdown_event.is_set() or refreshed_task.status == TaskStatus.PAUSED:
            return
        if refreshed_task.status == TaskStatus.COMPLETED:
            # Ensure at least one actionable WORK task exists if planner produced none.
            work_tasks = [
                t for t in self.store.list_tasks(run_rec.run_id) if t.kind != TaskKind.PLAN
            ]
            if not work_tasks:
                self.store.add_task(
                    run_rec.run_id,
                    f"Execute goal: {run_rec.goal[:80]}",
                    run_rec.goal,
                    kind=TaskKind.WORK,
                    role="worker",
                    tier="default",
                    budget=self.config.budgets.to_task_budget(),
                )
            self.store.mark_plan_materialized(run_rec.run_id)
            self.store.transition_run_phase(
                run_rec.run_id,
                RunPhase.RUNNING,
                actor="coordinator",
                reason="plan materialized",
            )
        elif refreshed_task.status == TaskStatus.FAILED:
            self.store.transition_run_phase(
                run_rec.run_id,
                RunPhase.FAILED,
                actor="coordinator",
                error_message="planning task failed",
            )

    def _handle_running(self, run_rec: RunRecord) -> None:
        self._run_worker_pool(run_rec.run_id, kinds=(TaskKind.WORK, TaskKind.SYNTHESIZE))
        if self._shutdown_event.is_set():
            return

        latest_run = self.store.get_run(run_rec.run_id)
        assert latest_run is not None
        if latest_run.phase != RunPhase.RUNNING:
            return

        tasks = self.store.list_tasks(run_rec.run_id)
        if any(t.status == TaskStatus.PAUSED for t in tasks):
            self.store.transition_run_phase(
                run_rec.run_id,
                RunPhase.PAUSED,
                actor="coordinator",
                reason="paused task awaiting operator resume",
            )
            return

        non_terminal = [
            t
            for t in tasks
            if t.status
            in (TaskStatus.PENDING, TaskStatus.READY, TaskStatus.RUNNING, TaskStatus.PAUSED)
        ]
        if non_terminal:
            return

        self._sync_drost_if_configured(latest_run)
        completed_work = [
            t
            for t in tasks
            if t.kind in (TaskKind.WORK, TaskKind.SYNTHESIZE)
            and t.status == TaskStatus.COMPLETED
        ]
        prior_verifies = [t for t in tasks if t.kind == TaskKind.VERIFY]
        if (
            self.config.run.enable_verify_phase
            and completed_work
            and not any(t.status == TaskStatus.COMPLETED for t in prior_verifies)
        ):
            self.store.transition_run_phase(
                run_rec.run_id,
                RunPhase.VERIFYING,
                actor="coordinator",
                reason="work finished; entering verification",
            )
        else:
            self.store.transition_run_phase(
                run_rec.run_id,
                RunPhase.COMPLETED,
                actor="coordinator",
                reason="all tasks settled",
            )

    def _handle_verifying(self, run_rec: RunRecord) -> None:
        tasks = self.store.list_tasks(run_rec.run_id)
        verify_tasks = [t for t in tasks if t.kind == TaskKind.VERIFY]
        if not any(
            t.status in (TaskStatus.PENDING, TaskStatus.READY, TaskStatus.RUNNING)
            for t in verify_tasks
        ):
            self.store.add_task(
                run_rec.run_id,
                "Independent verification review",
                (
                    "Review all facts, hypotheses, findings, and artifact references on the blackboard "
                    "with fresh skepticism. Verify evidence grounding and consistency. Propose follow-up "
                    "tasks only if a critical gap requires additional work."
                ),
                kind=TaskKind.VERIFY,
                role="verifier",
                tier="strong",
                priority=100,
                budget=self.config.budgets.to_task_budget(),
            )

        self._run_worker_pool(run_rec.run_id, kinds=(TaskKind.VERIFY,))
        if self._shutdown_event.is_set():
            return

        latest_run = self.store.get_run(run_rec.run_id)
        assert latest_run is not None
        if latest_run.phase != RunPhase.VERIFYING:
            return

        tasks = self.store.list_tasks(run_rec.run_id)
        if any(
            t.kind != TaskKind.VERIFY
            and t.status in (TaskStatus.PENDING, TaskStatus.READY, TaskStatus.RUNNING)
            for t in tasks
        ):
            self.store.transition_run_phase(
                run_rec.run_id,
                RunPhase.RUNNING,
                actor="coordinator",
                reason="verification requested follow-up tasks",
            )
            return

        if any(t.status == TaskStatus.PAUSED for t in tasks):
            self.store.transition_run_phase(
                run_rec.run_id,
                RunPhase.PAUSED,
                actor="coordinator",
                reason="paused task awaiting operator resume",
            )
            return

        self.store.transition_run_phase(
            run_rec.run_id,
            RunPhase.COMPLETED,
            actor="coordinator",
            reason="verification complete",
        )

    def _route_pair(self, role: str, tier: str) -> tuple[str, str]:
        routes = self.router.resolve_routes(role=role, tier=tier)
        return routes[0].provider, routes[0].model

    def _run_worker_pool(self, run_id: str, *, kinds: tuple[TaskKind, ...]) -> None:
        max_workers = self.config.run.max_workers
        active: dict[Future[None], tuple[str, str, int, threading.Event]] = {}

        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="drostpp-worker") as pool:
            while True:
                # Drain any completed futures first.
                for fut in list(active):
                    if fut.done():
                        active.pop(fut)
                        fut.result()

                # Reclaim expired leases and terminate lingering owners.
                expired = self.store.reclaim_expired_leases(run_id)
                for exp_att in expired:
                    for _f, (tid, aid, _gen, ev) in active.items():
                        if aid == exp_att.attempt_id or tid == exp_att.task_id:
                            ev.set()
                    if exp_att.pgid:
                        terminate_process_group(exp_att.pgid, grace_seconds=0.5)
                    if exp_att.container_id:
                        self.docker.force_remove_container(exp_att.container_id)
                    self.resources.release_attempt(exp_att.attempt_id)
                self.resources.reap(run_id)

                run_rec = self.store.get_run(run_id)
                assert run_rec is not None
                if self._shutdown_event.is_set() or run_rec.phase not in (
                    RunPhase.RUNNING,
                    RunPhase.VERIFYING,
                ):
                    for _f, (_tid, _aid, _gen, ev) in active.items():
                        ev.set()
                    if active:
                        wait(list(active.keys()), timeout=5.0)
                    for fut in list(active):
                        if fut.done():
                            active.pop(fut)
                            fut.result()
                    break

                # Admit new work up to max_workers.
                while len(active) < max_workers and not self._shutdown_event.is_set():
                    latest_run = self.store.get_run(run_id)
                    assert latest_run is not None
                    try:
                        disk_bytes = self.budget_tracker.check_run_admission(
                            latest_run,
                            self.state_dir,
                            reserve_memory_mb=(
                                (len(active) + 1)
                                * self.config.budgets.default_task_memory_mb
                            ),
                        )
                        self.store.update_run_disk_bytes(run_id, disk_bytes)
                    except BudgetExceededError as exc:
                        for _f, (_tid, _aid, _gen, ev) in active.items():
                            ev.set()
                        if active:
                            wait(list(active.keys()), timeout=5.0)
                        self.store.transition_run_phase(
                            run_id,
                            RunPhase.FAILED,
                            actor="coordinator",
                            error_message=str(exc),
                        )
                        return

                    claimed = self.store.claim_next_task(
                        run_id,
                        f"worker-{len(active)}",
                        "pending",
                        "",
                        lease_seconds=self.config.run.lease_seconds,
                        kinds=kinds,
                        route_resolver=self._route_pair,
                    )
                    if claimed is None:
                        break
                    task, attempt = claimed
                    cancel_ev = threading.Event()
                    fut = pool.submit(
                        self._execute_claimed_task,
                        latest_run,
                        task,
                        attempt,
                        cancel_ev,
                    )
                    active[fut] = (task.task_id, attempt.attempt_id, attempt.generation, cancel_ev)

                if not active:
                    break

                wait(list(active.keys()), timeout=0.1, return_when=FIRST_COMPLETED)

    def _execute_claimed_task(
        self,
        run_rec: RunRecord,
        task: TaskRecord,
        attempt: AttemptRecord,
        cancel_ev: threading.Event,
    ) -> None:
        attempt_dir = (
            self.state_dir / "runs" / run_rec.run_id / "attempts" / attempt.attempt_id
        )
        attempt_dir.mkdir(parents=True, exist_ok=True)
        task_budget = TaskBudget.from_dict(json.loads(task.budget_json))

        # Assign exploration diversity framing.
        assignment = self.diversity.assign_for_attempt(
            self.store,
            run_rec.run_id,
            run_rec.seed,
            task.task_id,
            attempt.generation,
        )
        diversity_block = self.diversity.render_framing(
            assignment,
            self.blackboard,
            run_id=run_rec.run_id,
            task_id=task.task_id,
        )
        bb_context = self.blackboard.render_context(
            run_rec.run_id,
            max_chars=10_000,
            exclude_task_id=task.task_id,
        )
        managed_resources = self.store.list_attempt_managed_resources(attempt.attempt_id)
        prompt = self._build_worker_prompt(
            run_rec=run_rec,
            task=task,
            diversity_block=diversity_block,
            blackboard_context=bb_context,
            managed_resources=managed_resources,
        )

        hb_stop = threading.Event()
        hb_interval = min(
            self.config.run.heartbeat_seconds,
            max(1.0, self.config.run.lease_seconds / 3.0),
        )

        def _hb_loop() -> None:
            while not hb_stop.wait(hb_interval):
                if self._shutdown_event.is_set() or cancel_ev.is_set():
                    break
                try:
                    self.store.heartbeat_attempt(
                        task.task_id,
                        attempt.attempt_id,
                        attempt.generation,
                        lease_seconds=self.config.run.lease_seconds,
                    )
                except FencedAttemptError:
                    cancel_ev.set()
                    break
                except Exception:
                    break

        hb_thread = threading.Thread(target=_hb_loop, daemon=True)
        hb_thread.start()

        def _on_runtime(pid: int | None, pgid: int | None, cid: str | None) -> None:
            try:
                self.store.attach_attempt_runtime(
                    task.task_id,
                    attempt.attempt_id,
                    attempt.generation,
                    pid=pid,
                    pgid=pgid,
                    container_id=cid,
                )
            except FencedAttemptError:
                cancel_ev.set()

        def _on_hb(in_tok: int | None, out_tok: int | None, tot_tok: int | None) -> None:
            try:
                self.store.heartbeat_attempt(
                    task.task_id,
                    attempt.attempt_id,
                    attempt.generation,
                    lease_seconds=self.config.run.lease_seconds,
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                    total_tokens=tot_tok,
                )
            except FencedAttemptError:
                cancel_ev.set()

        routes = self.router.resolve_routes(role=task.role, tier=task.tier)
        mcp_servers = self._active_mcp_servers(
            run_rec.run_id,
            task.task_id,
            attempt.attempt_id,
            attempt.generation,
        )
        final_result = AttemptResult(
            success=False,
            error_kind=ErrorKind.HARD_ERROR,
            error_message="no configured routes",
        )

        try:
            for route in routes:
                if self._shutdown_event.is_set() or cancel_ev.is_set():
                    final_result = AttemptResult(
                        success=False,
                        error_kind=ErrorKind.HARD_ERROR,
                        error_message="cancelled before dispatch",
                        cancelled=True,
                    )
                    break

                adapter = self.adapters.get(route.provider)
                if adapter is None:
                    final_result = AttemptResult(
                        success=False,
                        error_kind=ErrorKind.HARD_ERROR,
                        error_message=f"no adapter registered for provider {route.provider!r}",
                    )
                    continue

                ctx = AttemptContext(
                    run_id=run_rec.run_id,
                    task=task,
                    attempt=attempt,
                    prompt=prompt,
                    attempt_dir=attempt_dir,
                    workspace_dir=self.workspace_dir,
                    budget=task_budget,
                    route=route,
                    mcp_servers=mcp_servers,
                    cancel_event=cancel_ev,
                    on_runtime_attached=_on_runtime,
                    on_heartbeat=_on_hb,
                    env={
                        "DROSTPP_STATE_DIR": str(self.state_dir),
                        "DROSTPP_RUN_ID": run_rec.run_id,
                        "DROSTPP_TASK_ID": task.task_id,
                        "DROSTPP_ATTEMPT_ID": attempt.attempt_id,
                        "DROSTPP_GENERATION": str(attempt.generation),
                        **(
                            {
                                "DROSTPP_REAL_DOCKER_HOST": os.environ.get("DOCKER_HOST", ""),
                                "DOCKER_HOST": (
                                    f"unix://{self.state_dir}/managed-containers-only.sock"
                                ),
                            }
                            if self.config.container.enabled
                            and self.config.container.block_direct_docker
                            else {}
                        ),
                    },
                )
                try:
                    res = adapter.execute(ctx)
                except Exception as exc:
                    res = AttemptResult(
                        success=False,
                        error_kind=ErrorKind.HARD_ERROR,
                        error_message=f"adapter {route.provider} raised {type(exc).__name__}: {exc}",
                    )

                self.router.record_outcome(route, res.error_kind)
                final_result = res
                if res.success or res.cancelled or self._shutdown_event.is_set():
                    break
                if res.error_kind not in (ErrorKind.QUOTA, ErrorKind.TRANSIENT):
                    break
        finally:
            hb_stop.set()
            hb_thread.join(timeout=1.0)

        disk_used = compute_dir_bytes(attempt_dir)

        try:
            if self._shutdown_event.is_set() or final_result.cancelled:
                self.store.interrupt_attempt(
                    task.task_id,
                    attempt.attempt_id,
                    attempt.generation,
                    reason="coordinator shutdown/cancelled",
                    input_tokens=final_result.input_tokens,
                    output_tokens=final_result.output_tokens,
                    total_tokens=final_result.total_tokens,
                )
                return

            if not final_result.success or final_result.output is None:
                err_msg = final_result.error_message or "worker attempt failed"
                sig = error_signature(final_result.error_kind, err_msg)
                self.store.fail_attempt(
                    task.task_id,
                    attempt.attempt_id,
                    attempt.generation,
                    error_kind=final_result.error_kind,
                    error_message=err_msg,
                    error_sig=sig,
                    max_same_error_repeats=self.config.budgets.max_same_error_repeats,
                    input_tokens=final_result.input_tokens,
                    output_tokens=final_result.output_tokens,
                    total_tokens=final_result.total_tokens,
                    disk_bytes=disk_used,
                    cancelled=final_result.cancelled,
                )
                return

            output = final_result.output
            self._commit_blackboard_items(run_rec.run_id, task, attempt, output)

            if output.status == "blocked":
                reason = output.blocker_reason or output.summary or "worker reported blocked"
                self.store.fail_attempt(
                    task.task_id,
                    attempt.attempt_id,
                    attempt.generation,
                    error_kind=ErrorKind.HARD_ERROR,
                    error_message=reason,
                    error_sig=error_signature(ErrorKind.HARD_ERROR, reason),
                    max_same_error_repeats=self.config.budgets.max_same_error_repeats,
                    input_tokens=final_result.input_tokens,
                    output_tokens=final_result.output_tokens,
                    total_tokens=final_result.total_tokens,
                    disk_bytes=disk_used,
                    force_terminal=True,
                )
                return

            created_follow_ups = self._enqueue_follow_ups(
                run_rec.run_id,
                task,
                output.follow_up_tasks,
            )
            self._apply_resource_handoffs(
                run_rec.run_id,
                task.task_id,
                attempt.attempt_id,
                attempt.generation,
                output,
                created_follow_ups,
            )
            self.store.complete_attempt(
                task.task_id,
                attempt.attempt_id,
                attempt.generation,
                result={
                    "status": output.status,
                    "summary": output.summary,
                    "follow_up_ids": created_follow_ups,
                },
                input_tokens=final_result.input_tokens,
                output_tokens=final_result.output_tokens,
                total_tokens=final_result.total_tokens,
                disk_bytes=disk_used,
            )
        except FencedAttemptError:
            # Stale worker was fenced; rejection audit already recorded in store.
            return
        finally:
            self.resources.release_attempt(attempt.attempt_id)

    def _apply_resource_handoffs(
        self,
        run_id: str,
        task_id: str,
        attempt_id: str,
        generation: int,
        output: WorkerOutput,
        created_follow_up_ids: list[str],
    ) -> None:
        """Reserve explicitly named resources only for follow-ups created by this output."""
        if not output.resource_handoffs:
            return
        created_tasks = [
            task
            for task_id in created_follow_up_ids
            if (task := self.store.get_task(task_id)) is not None
        ]
        title_to_id = {task.title.strip().lower(): task.task_id for task in created_tasks}
        seen_keys: set[str] = set()
        for handoff in output.resource_handoffs:
            normalized_title = handoff.to_task_title.strip().lower()
            target_id = title_to_id.get(normalized_title)
            if target_id is None:
                continue
            if handoff.resource_key in seen_keys:
                continue
            try:
                self.resources.handoff(
                    run_id=run_id,
                    from_attempt_id=attempt_id,
                    to_task_id=target_id,
                    resource_key=handoff.resource_key,
                )
                seen_keys.add(handoff.resource_key)
            except (IllegalTransitionError, ValueError) as exc:
                self.blackboard.publish(
                    run_id,
                    BlackboardKind.NOTE,
                    "Managed resource handoff rejected",
                    (
                        f"Resource {handoff.resource_key!r} was not kept for "
                        f"{handoff.to_task_title!r}: {exc}"
                    ),
                    task_id=task_id,
                    attempt_id=attempt_id,
                    generation=generation,
                    tags=["resource", "handoff", "warning"],
                    confidence=1.0,
                )

    def _commit_blackboard_items(
        self,
        run_id: str,
        task: TaskRecord,
        attempt: AttemptRecord,
        output: WorkerOutput,
    ) -> None:
        groups = [
            (BlackboardKind.FACT, output.facts),
            (BlackboardKind.HYPOTHESIS, output.hypotheses),
            (BlackboardKind.FINDING, output.findings),
            (BlackboardKind.NOTE, output.notes),
        ]
        for kind, items in groups:
            for item in items:
                self.blackboard.publish(
                    run_id,
                    kind,
                    str(item.get("title", "")),
                    str(item.get("body", "")),
                    task_id=task.task_id,
                    attempt_id=attempt.attempt_id,
                    generation=attempt.generation,
                    tags=item.get("tags") or [],
                    confidence=float(item.get("confidence", 0.6)),
                )

    def _enqueue_follow_ups(
        self,
        run_id: str,
        parent: TaskRecord,
        proposals: list[FollowUpProposal],
    ) -> list[str]:
        if not proposals or self.config.run.max_follow_ups_per_task <= 0:
            return []

        existing_tasks = self.store.list_tasks(run_id)
        remaining_run_slots = max(0, self.config.run.max_total_tasks - len(existing_tasks))
        limit = min(self.config.run.max_follow_ups_per_task, remaining_run_slots)
        if limit <= 0:
            return []

        title_to_id = {t.title.strip().lower(): t.task_id for t in existing_tasks}
        created_ids: list[str] = []

        for prop in proposals:
            if len(created_ids) >= limit:
                break
            norm_title = prop.title.strip().lower()
            if not norm_title or norm_title in title_to_id:
                continue
            dep_ids: list[str] = []
            for dep_title in prop.depends_on_titles:
                dep_id = title_to_id.get(dep_title.strip().lower())
                if dep_id:
                    dep_ids.append(dep_id)

            new_task = self.store.add_task(
                run_id,
                prop.title,
                prop.prompt,
                kind=prop.kind,
                role=prop.role,
                tier=prop.tier,
                priority=prop.priority,
                budget=self.config.budgets.to_task_budget(),
                depends_on=dep_ids,
                metadata={"parent_task_id": parent.task_id},
                actor=parent.task_id,
            )
            title_to_id[norm_title] = new_task.task_id
            created_ids.append(new_task.task_id)

        return created_ids

    def _build_worker_prompt(
        self,
        *,
        run_rec: RunRecord,
        task: TaskRecord,
        diversity_block: str,
        blackboard_context: str,
        managed_resources: list[ManagedResource],
    ) -> str:
        drost_section = ""
        if self.config.drost.enabled:
            eng_hint = (
                f"Use Drost engagement_id `{run_rec.drost_engagement_id}` for any Drost MCP tool calls."
                if run_rec.drost_engagement_id
                else "List or select a Drost engagement via `drost_engagement_list` / `drost_engagement_get` before calling engagement-scoped Drost tools."
            )
            drost_section = (
                "\n## External Tool Workspace (Drost MCP)\n"
                f"{eng_hint}\n"
                f"Configured Drost MCP mode: `{self.config.drost.mcp_mode}`.\n"
            )

        resource_section = ""
        if self.config.container.enabled:
            reservations = (
                "\n".join(
                    f"- `{resource.resource_key}`: container `{resource.name}` "
                    f"(id `{resource.external_id[:12]}`)"
                    for resource in managed_resources
                )
                if managed_resources
                else "- None"
            )
            resource_section = (
                "\n## Managed Container Ownership\n"
                "All task-created Docker containers MUST go through the Drost++ resource broker. "
                "Do not invoke `docker run` directly. Prefer the `drostpp_resources` MCP tools; "
                "from a shell, start one with "
                "`drost++ resource start --key NAME --image IMAGE -- COMMAND...`; borrow an "
                "existing one with `drost++ resource borrow --key NAME`. The broker applies RAM, "
                "PID, log, and writable-layer caps. It removes the container when the last borrower "
                "exits. To keep one only for an immediate follow-up, include both that follow-up in "
                "`follow_up_tasks` and `{\"resource_key\": NAME, \"to_task_title\": TITLE}` in "
                "`resource_handoffs`. Handoffs expire quickly if the consumer does not start.\n"
                "Resources already reserved for this task:\n"
                f"{reservations}\n"
            )

        return (
            f"# Orchestration Task ({task.kind.upper()} / role={task.role})\n"
            f"Run ID: {run_rec.run_id}\n"
            f"Task ID: {task.task_id} (generation {task.generation})\n\n"
            f"## Overall Goal\n{run_rec.goal}\n\n"
            f"## Task Mandate: {task.title}\n{task.prompt}\n\n"
            f"## Diversity & Exploration Framing\n{diversity_block}\n"
            f"{drost_section}\n"
            f"{resource_section}\n"
            f"## Shared Blackboard Context\n{blackboard_context}\n\n"
            "## Required Response Format\n"
            "Respond with a single JSON object conforming strictly to this schema:\n"
            f"```json\n{json.dumps(WORKER_OUTPUT_JSON_SCHEMA, indent=2)}\n```\n"
        )
