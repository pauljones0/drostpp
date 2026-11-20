"""Tests for managed-container ownership, borrowing, handoff, expiry, and caps."""

from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from drostpp.adapters.mock import MockAdapter
from drostpp.config import ContainerConfig, OrchestratorConfig
from drostpp.coordinator import Coordinator
from drostpp.integrations.mcp import McpStdioClient
from drostpp.models import (
    AttemptResult,
    FollowUpProposal,
    McpServerConfig,
    ResourceHandoff,
    ResourceStatus,
    RunPhase,
    WorkerOutput,
)
from drostpp.resources import ResourceManager
from drostpp.store import SQLiteStore


class FakeDockerRunner:
    def __init__(self) -> None:
        self.containers: dict[str, dict[str, object]] = {}
        self.removed: list[str] = []
        self.argv: list[str] = []
        self.next_id = 1
        self.pending_kwargs: dict[str, object] = {}

    def build_run_argv(self, **kwargs) -> list[str]:
        argv = [
            "fake-docker",
            kwargs["container_name"],
            "--memory",
            str(kwargs["memory_mb"]),
            "--pids-limit",
            str(kwargs["pids_limit"]),
        ]
        for port in kwargs.get("ports") or []:
            argv.extend(["--publish", port])
        self.argv = argv
        self.pending_kwargs = dict(kwargs)
        return argv

    def run_detached(self, _argv: list[str], timeout: float = 60.0) -> str:
        container_id = f"container-{self.next_id}"
        self.next_id += 1
        self.containers[container_id] = {
            "State": {"Running": True},
            "SizeRw": 0,
            "Config": {
                "Labels": {
                    "drostpp.managed": "true",
                    "drostpp.run_id": str(self.pending_kwargs.get("run_id", "")),
                    "drostpp.resource_id": str(self.pending_kwargs.get("resource_id", "")),
                }
            },
        }
        return container_id

    def inspect_container(self, container_id: str, timeout: float = 10.0):
        return self.containers.get(container_id)

    def force_remove_container(self, container_id: str, timeout: float = 10.0) -> bool:
        self.removed.append(container_id)
        return self.containers.pop(container_id, None) is not None

    def list_managed_containers(self, run_id: str, timeout: float = 10.0) -> list[str]:
        return [
            container_id
            for container_id, inspection in self.containers.items()
            if inspection.get("Config", {}).get("Labels", {}).get("drostpp.run_id") == run_id
        ]

    def exec_container(
        self,
        container_id: str,
        command: list[str],
        *,
        timeout: float = 300.0,
        max_output_bytes: int = 2 * 1024 * 1024,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, f"{container_id}:{' '.join(command)}", "")


def _running_store(tmp_path: Path) -> tuple[SQLiteStore, str]:
    store = SQLiteStore(tmp_path / "drostpp.db")
    run = store.create_run("resource leases")
    store.transition_run_phase(run.run_id, RunPhase.PLANNING)
    store.mark_plan_materialized(run.run_id)
    store.transition_run_phase(run.run_id, RunPhase.RUNNING)
    return store, run.run_id


def _manager(store: SQLiteStore, docker: FakeDockerRunner, **overrides) -> ResourceManager:
    cfg = ContainerConfig(enabled=True, **overrides)
    return ResourceManager(store, cfg, docker=docker, attempt_lease_seconds=60)


def test_last_borrower_removes_container_and_caps_are_in_argv(tmp_path: Path) -> None:
    store, run_id = _running_store(tmp_path)
    docker = FakeDockerRunner()
    manager = _manager(store, docker, memory_mb=384, pids_limit=32)
    try:
        task1 = store.add_task(run_id, "first", "first")
        task2 = store.add_task(run_id, "second", "second")
        claim1 = store.claim_next_task(run_id, "w1", "mock", "m")
        claim2 = store.claim_next_task(run_id, "w2", "mock", "m")
        assert claim1 is not None and claim1[0].task_id == task1.task_id
        assert claim2 is not None and claim2[0].task_id == task2.task_id

        resource = manager.start_container(
            run_id=run_id,
            task_id=task1.task_id,
            attempt_id=claim1[1].attempt_id,
            generation=claim1[1].generation,
            resource_key="shared-scanner",
            image="scanner:test",
            command=["sleep", "600"],
            publish_container_ports=[8080],
        )
        borrowed = manager.borrow_container(
            run_id=run_id,
            task_id=task2.task_id,
            attempt_id=claim2[1].attempt_id,
            generation=claim2[1].generation,
            resource_key="shared-scanner",
        )
        assert borrowed.resource_id == resource.resource_id
        assert "127.0.0.1::8080" in docker.argv
        assert docker.argv[docker.argv.index("--memory") + 1] == "384"
        assert docker.argv[docker.argv.index("--pids-limit") + 1] == "32"

        manager.release_attempt(claim1[1].attempt_id)
        assert docker.removed == []
        manager.release_attempt(claim2[1].attempt_id)
        assert docker.removed == [resource.external_id]
        assert store.get_managed_resource(run_id, "shared-scanner").status == ResourceStatus.STOPPED
    finally:
        store.close()


def test_task_handoff_transfers_to_claimed_attempt_then_reclaims(tmp_path: Path) -> None:
    store, run_id = _running_store(tmp_path)
    docker = FakeDockerRunner()
    manager = _manager(store, docker, handoff_seconds=30)
    try:
        parent = store.add_task(run_id, "producer", "produce")
        parent_claim = store.claim_next_task(run_id, "producer", "mock", "m")
        assert parent_claim is not None
        resource = manager.start_container(
            run_id=run_id,
            task_id=parent.task_id,
            attempt_id=parent_claim[1].attempt_id,
            generation=parent_claim[1].generation,
            resource_key="target-lab",
            image="lab:test",
        )
        child = store.add_task(
            run_id,
            "immediate consumer",
            "consume",
            depends_on=[parent.task_id],
        )
        manager.handoff(
            run_id=run_id,
            from_attempt_id=parent_claim[1].attempt_id,
            to_task_id=child.task_id,
            resource_key="target-lab",
        )
        manager.release_attempt(parent_claim[1].attempt_id)
        assert docker.removed == []

        store.complete_attempt(
            parent.task_id,
            parent_claim[1].attempt_id,
            parent_claim[1].generation,
        )
        child_claim = store.claim_next_task(run_id, "consumer", "mock", "m")
        assert child_claim is not None and child_claim[0].task_id == child.task_id
        reservations = store.list_attempt_managed_resources(child_claim[1].attempt_id)
        assert [item.resource_key for item in reservations] == ["target-lab"]

        manager.release_attempt(child_claim[1].attempt_id)
        assert docker.removed == [resource.external_id]
    finally:
        store.close()


def test_expired_reservation_and_disk_overage_are_reaped(tmp_path: Path) -> None:
    store, run_id = _running_store(tmp_path)
    docker = FakeDockerRunner()
    manager = _manager(store, docker, disk_limit_bytes=1024)
    try:
        task = store.add_task(run_id, "producer", "produce")
        claimed = store.claim_next_task(run_id, "producer", "mock", "m")
        assert claimed is not None
        resource = manager.start_container(
            run_id=run_id,
            task_id=task.task_id,
            attempt_id=claimed[1].attempt_id,
            generation=claimed[1].generation,
            resource_key="disk-hog",
            image="hog:test",
        )
        docker.containers[resource.external_id]["SizeRw"] = 2048
        result = manager.reap(run_id)
        assert result["disk_exceeded"] == ["disk-hog"]
        assert resource.external_id in docker.removed

        resource2 = manager.start_container(
            run_id=run_id,
            task_id=task.task_id,
            attempt_id=claimed[1].attempt_id,
            generation=claimed[1].generation,
            resource_key="expires",
            image="sleep:test",
        )
        with store._txn() as conn:
            conn.execute(
                "UPDATE resource_leases SET expires_at = ? WHERE resource_id = ?",
                (datetime(2000, 1, 1, tzinfo=UTC).isoformat(), resource2.resource_id),
            )
        result2 = manager.reap(run_id)
        assert result2["stopped"] == ["expires"]
        assert resource2.external_id in docker.removed
    finally:
        store.close()


def test_exec_renews_borrow_and_returns_output(tmp_path: Path) -> None:
    store, run_id = _running_store(tmp_path)
    docker = FakeDockerRunner()
    manager = _manager(store, docker)
    try:
        task = store.add_task(run_id, "executor", "execute")
        claimed = store.claim_next_task(run_id, "executor", "mock", "m")
        assert claimed is not None
        manager.start_container(
            run_id=run_id,
            task_id=task.task_id,
            attempt_id=claimed[1].attempt_id,
            generation=claimed[1].generation,
            resource_key="toolbox",
            image="toolbox:test",
        )
        resource, code, stdout, stderr = manager.exec_container(
            run_id=run_id,
            task_id=task.task_id,
            attempt_id=claimed[1].attempt_id,
            generation=claimed[1].generation,
            resource_key="toolbox",
            command=["scan", "target"],
        )
        assert code == 0
        assert stdout == f"{resource.external_id}:scan target"
        assert stderr == ""
    finally:
        manager.release_attempt(claimed[1].attempt_id)
        store.close()


def test_prepared_container_is_recoverable_and_stopping_state_blocks_new_borrows(
    tmp_path: Path,
) -> None:
    """Crash gaps cannot create an unowned container or admit a late borrower."""
    store, run_id = _running_store(tmp_path)
    docker = FakeDockerRunner()
    manager = _manager(store, docker)
    try:
        first = store.add_task(run_id, "starter", "start")
        second = store.add_task(run_id, "late borrower", "borrow")
        claim1 = store.claim_next_task(run_id, "starter", "mock", "m")
        claim2 = store.claim_next_task(run_id, "late", "mock", "m")
        assert claim1 is not None and claim2 is not None
        prepared = store.prepare_managed_resource(
            run_id=run_id,
            resource_key="crash-gap",
            kind="docker-container",
            name="dpp-crash-gap",
            memory_limit_mb=256,
            disk_limit_bytes=1024,
            task_id=first.task_id,
            attempt_id=claim1[1].attempt_id,
            generation=claim1[1].generation,
            lease_seconds=60,
        )
        # Simulate Docker succeeding, then the broker dying before activation persisted the ID.
        docker.containers[prepared.name] = {
            "State": {"Running": True},
            "SizeRw": 0,
            "Config": {
                "Labels": {
                    "drostpp.managed": "true",
                    "drostpp.run_id": run_id,
                    "drostpp.resource_id": prepared.resource_id,
                }
            },
        }
        reclaimable = store.release_attempt_resource_leases(claim1[1].attempt_id)
        assert len(reclaimable) == 1
        assert reclaimable[0].status == ResourceStatus.STOPPING

        from drostpp.models import IllegalTransitionError

        with pytest.raises(IllegalTransitionError):
            manager.borrow_container(
                run_id=run_id,
                task_id=second.task_id,
                attempt_id=claim2[1].attempt_id,
                generation=claim2[1].generation,
                resource_key="crash-gap",
            )

        result = manager.reap(run_id)
        assert result["stopped"] == ["crash-gap"]
        assert prepared.name in docker.removed
        assert store.get_managed_resource(run_id, "crash-gap").status == ResourceStatus.STOPPED
    finally:
        store.close()


def test_reaper_adopts_container_created_before_activation_write(tmp_path: Path) -> None:
    store, run_id = _running_store(tmp_path)
    docker = FakeDockerRunner()
    manager = _manager(store, docker)
    try:
        task = store.add_task(run_id, "starter", "start")
        claimed = store.claim_next_task(run_id, "starter", "mock", "m")
        assert claimed is not None
        prepared = store.prepare_managed_resource(
            run_id=run_id,
            resource_key="adopt-me",
            kind="docker-container",
            name="dpp-adopt-me",
            memory_limit_mb=256,
            disk_limit_bytes=1024,
            task_id=task.task_id,
            attempt_id=claimed[1].attempt_id,
            generation=claimed[1].generation,
            lease_seconds=60,
        )
        container_id = "container-adopted"
        docker.containers[container_id] = {
            "State": {"Running": True},
            "SizeRw": 0,
            "Config": {
                "Labels": {
                    "drostpp.managed": "true",
                    "drostpp.run_id": run_id,
                    "drostpp.resource_id": prepared.resource_id,
                }
            },
        }
        result = manager.reap(run_id)
        assert result["adopted"] == ["adopt-me"]
        adopted = store.get_managed_resource(run_id, "adopt-me")
        assert adopted.status == ResourceStatus.RUNNING
        assert adopted.external_id == container_id
        manager.release_attempt(claimed[1].attempt_id)
        assert container_id in docker.removed
    finally:
        store.close()


def test_resource_mcp_is_automatically_usable_by_api_workers(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "drostpp.db")
    try:
        from drostpp.config import OrchestratorConfig

        cfg = OrchestratorConfig()
        cfg.container.enabled = True
        cfg.budgets.min_available_memory_mb = 0
        cfg.budgets.min_free_disk_bytes = 0
        run = store.create_run("resource mcp", config=cfg.to_public_dict())
        store.transition_run_phase(run.run_id, RunPhase.PLANNING)
        store.mark_plan_materialized(run.run_id)
        store.transition_run_phase(run.run_id, RunPhase.RUNNING)
        task = store.add_task(run.run_id, "mcp worker", "list resources")
        claimed = store.claim_next_task(run.run_id, "worker", "mock", "m")
        assert claimed is not None

        server = McpServerConfig(
            name="resources",
            command=sys.executable,
            args=["-m", "drostpp.resource_mcp"],
            env={
                "DROSTPP_STATE_DIR": str(tmp_path),
                "DROSTPP_RUN_ID": run.run_id,
                "DROSTPP_TASK_ID": task.task_id,
                "DROSTPP_ATTEMPT_ID": claimed[1].attempt_id,
                "DROSTPP_GENERATION": str(claimed[1].generation),
            },
            timeout_seconds=5.0,
        )
        with McpStdioClient(server) as client:
            names = {tool["name"] for tool in client.list_tools()}
            assert names == {
                "resource_start",
                "resource_borrow",
                "resource_exec",
                "resource_release",
                "resource_list",
            }
            assert client.call_tool("resource_list", {}) == "[]"
    finally:
        store.close()


def test_invalid_handoff_is_rejected_without_crashing_run(tmp_path: Path) -> None:
    cfg = OrchestratorConfig()
    cfg.run.enable_verify_phase = False
    cfg.budgets.min_available_memory_mb = 0

    def worker(ctx):
        if ctx.task.title == "parent":
            return AttemptResult(
                success=True,
                output=WorkerOutput(
                    status="needs_follow_up",
                    summary="follow up",
                    follow_up_tasks=[FollowUpProposal(title="child", prompt="finish")],
                    resource_handoffs=[
                        ResourceHandoff(
                            resource_key="not-owned", to_task_title="child"
                        )
                    ],
                ),
            )
        return AttemptResult(
            success=True,
            output=WorkerOutput(status="completed", summary="done"),
        )

    adapter = MockAdapter(worker)
    coord = Coordinator(
        tmp_path / "state",
        cfg,
        adapters={"codex": adapter, "kimi": adapter, "mock": adapter},
    )
    try:
        run = coord.create_run("handoff rejection")
        coord.store.transition_run_phase(run.run_id, RunPhase.PLANNING)
        coord.store.mark_plan_materialized(run.run_id)
        coord.store.transition_run_phase(run.run_id, RunPhase.RUNNING)
        coord.store.add_task(run.run_id, "parent", "work")
        with coord.acquire_lock():
            final = coord._drive_run(run.run_id)
        assert final.phase == RunPhase.COMPLETED
        warnings = [
            entry
            for entry in coord.store.list_blackboard_entries(run.run_id)
            if entry.title == "Managed resource handoff rejected"
        ]
        assert len(warnings) == 1
        assert "not-owned" in warnings[0].body
    finally:
        coord.close()
