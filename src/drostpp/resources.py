"""Durable ownership and lease management for worker-created Docker containers."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .config import ContainerConfig
from .models import (
    AttemptStatus,
    BudgetExceededError,
    IllegalTransitionError,
    ManagedResource,
    ResourceStatus,
    TaskBudget,
)
from .store import SQLiteStore
from .supervision import DockerRunner

_RESOURCE_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")


class ResourceManager:
    """Own managed containers until their final attempt/task lease is released."""

    def __init__(
        self,
        store: SQLiteStore,
        config: ContainerConfig,
        *,
        docker: DockerRunner | None = None,
        attempt_lease_seconds: int = 120,
        min_available_memory_mb: int = 0,
        min_free_disk_bytes: int = 0,
    ) -> None:
        self.store = store
        self.config = config
        self.docker = docker or DockerRunner(config.docker_binary)
        self.attempt_lease_seconds = max(5, int(attempt_lease_seconds))
        self.min_available_memory_mb = max(0, int(min_available_memory_mb))
        self.min_free_disk_bytes = max(0, int(min_free_disk_bytes))

    def start_container(
        self,
        *,
        run_id: str,
        task_id: str,
        attempt_id: str,
        generation: int,
        resource_key: str,
        image: str,
        command: list[str] | None = None,
        env: dict[str, str] | None = None,
        network: str | None = None,
        publish_container_ports: list[int] | None = None,
    ) -> ManagedResource:
        """Start a capped container, or borrow the live resource with the same key."""
        key = self._validated_key(resource_key)
        image = image.strip()
        if not image:
            raise ValueError("managed container image must not be empty")
        if any(port < 1 or port > 65535 for port in publish_container_ports or []):
            raise ValueError("published container ports must be between 1 and 65535")
        ports = [f"127.0.0.1::{int(port)}" for port in publish_container_ports or []]

        existing = self.store.get_managed_resource(run_id, key)
        if existing is not None and existing.status == ResourceStatus.PREPARING:
            raise IllegalTransitionError(f"managed resource {key!r} is already starting")
        if existing is not None and existing.status == ResourceStatus.STOPPING:
            self._stop_one(existing, reason="finish prior reclamation before restart")
            existing = self.store.get_managed_resource(run_id, key)
            if existing is not None and existing.status == ResourceStatus.STOPPING:
                raise IllegalTransitionError(f"managed resource {key!r} is still being reclaimed")
        if existing is not None and existing.status == ResourceStatus.RUNNING:
            inspection = self.docker.inspect_container(existing.external_id)
            if self._inspection_running(inspection):
                return self.borrow_container(
                    run_id=run_id,
                    task_id=task_id,
                    attempt_id=attempt_id,
                    generation=generation,
                    resource_key=key,
                )
            self.store.mark_managed_resource_stopped(
                existing.resource_id,
                lost=inspection is None,
                error="container disappeared before it could be borrowed",
            )

        self._check_host_admission(run_id)

        container_name = self._container_name(run_id, key)
        prepared = self.store.prepare_managed_resource(
            run_id=run_id,
            resource_key=key,
            kind="docker-container",
            name=container_name,
            memory_limit_mb=self.config.memory_mb,
            disk_limit_bytes=self.config.disk_limit_bytes,
            task_id=task_id,
            attempt_id=attempt_id,
            generation=generation,
            lease_seconds=self.attempt_lease_seconds,
            max_per_run=self.config.max_per_run,
            metadata={
                "image": image,
                "command": list(command or []),
                "published_container_ports": list(publish_container_ports or []),
            },
        )
        try:
            argv = self.docker.build_run_argv(
                image=image,
                command=list(command or []),
                run_id=run_id,
                attempt_id=attempt_id,
                generation=generation,
                container_name=container_name,
                memory_mb=self.config.memory_mb,
                pids_limit=self.config.pids_limit,
                network=network if network is not None else self.config.network,
                read_only=self.config.read_only,
                env=env,
                ports=ports,
                detach=True,
                auto_remove=False,
                log_max_size=self.config.log_max_size,
                log_max_files=self.config.log_max_files,
                resource_id=prepared.resource_id,
            )
            container_id = self.docker.run_detached(argv)
            activated = self.store.activate_managed_resource(
                resource_id=prepared.resource_id,
                external_id=container_id,
                task_id=task_id,
                attempt_id=attempt_id,
                generation=generation,
            )
            return activated
        except Exception:
            refreshed = self.store.get_managed_resource(run_id, key)
            if refreshed is not None and refreshed.resource_id == prepared.resource_id:
                self._stop_one(refreshed, reason="container start or activation failed")
            raise

    def borrow_container(
        self,
        *,
        run_id: str,
        task_id: str,
        attempt_id: str,
        generation: int,
        resource_key: str,
    ) -> ManagedResource:
        key = self._validated_key(resource_key)
        resource = self.store.borrow_managed_resource(
            run_id=run_id,
            resource_key=key,
            task_id=task_id,
            attempt_id=attempt_id,
            generation=generation,
            lease_seconds=self.attempt_lease_seconds,
        )
        inspection = self.docker.inspect_container(resource.external_id)
        if not self._inspection_running(inspection):
            self.store.mark_managed_resource_stopped(
                resource.resource_id,
                lost=inspection is None,
                error="borrowed container is no longer running",
            )
            raise IllegalTransitionError(f"managed resource {key!r} is no longer running")
        return resource

    def handoff(
        self,
        *,
        run_id: str,
        from_attempt_id: str,
        to_task_id: str,
        resource_key: str,
    ) -> ManagedResource:
        """Move one attempt lease to a short task reservation for an immediate consumer."""
        return self.store.reserve_managed_resource_for_task(
            run_id=run_id,
            resource_key=self._validated_key(resource_key),
            from_attempt_id=from_attempt_id,
            to_task_id=to_task_id,
            lease_seconds=self.config.handoff_seconds,
        )

    def exec_container(
        self,
        *,
        run_id: str,
        task_id: str,
        attempt_id: str,
        generation: int,
        resource_key: str,
        command: list[str],
        timeout: float = 300.0,
    ) -> tuple[ManagedResource, int, str, str]:
        resource = self.borrow_container(
            run_id=run_id,
            task_id=task_id,
            attempt_id=attempt_id,
            generation=generation,
            resource_key=resource_key,
        )
        try:
            result = self.docker.exec_container(
                resource.external_id,
                command,
                timeout=timeout,
                max_output_bytes=2 * 1024 * 1024,
            )
        except RuntimeError:
            self._stop_one(resource, reason="container exec supervision failed")
            raise
        inspection = self.docker.inspect_container(resource.external_id)
        if inspection is not None:
            writable_bytes = self._writable_bytes(inspection)
            if resource.disk_limit_bytes > 0 and writable_bytes > resource.disk_limit_bytes:
                self._stop_one(
                    resource,
                    reason=(
                        "container writable layer exceeded limit after exec "
                        f"({writable_bytes} > {resource.disk_limit_bytes} bytes)"
                    ),
                )
                message = (
                    f"managed container disk limit exceeded: {writable_bytes} > "
                    f"{resource.disk_limit_bytes} bytes"
                )
                stderr = f"{result.stderr.rstrip()}\n{message}\n".lstrip()
                return resource, 1, result.stdout, stderr
        return resource, result.returncode, result.stdout, result.stderr

    def release_container(self, attempt_id: str, resource_key: str) -> dict[str, list[str]]:
        reclaimable = self.store.release_attempt_resource_lease(
            attempt_id, self._validated_key(resource_key)
        )
        return self._stop_resources(reclaimable, reason="borrower explicitly released")

    def release_attempt(self, attempt_id: str) -> dict[str, list[str]]:
        """Drop an attempt's leases and synchronously remove now-unowned containers."""
        reclaimable = self.store.release_attempt_resource_leases(attempt_id)
        return self._stop_resources(reclaimable, reason="last borrower released")

    def reap(self, run_id: str) -> dict[str, list[str]]:
        """Expire abandoned leases and enforce container liveness and writable-layer caps."""
        result: dict[str, list[str]] = {
            "stopped": [],
            "lost": [],
            "disk_exceeded": [],
            "adopted": [],
            "orphaned": [],
            "errors": [],
        }
        self._merge(result, self._reconcile_labeled_containers(run_id))
        expired = self.store.expire_resource_leases(run_id)
        self._merge(result, self._stop_resources(expired, reason="lease expired"))

        retry_stopping = self.store.list_managed_resources(
            run_id, status=ResourceStatus.STOPPING
        )
        self._merge(
            result,
            self._stop_resources(retry_stopping, reason="retry interrupted reclamation"),
        )

        for resource in self.store.list_managed_resources(
            run_id, status=ResourceStatus.RUNNING
        ):
            inspection = self.docker.inspect_container(resource.external_id)
            if inspection is None:
                self.store.mark_managed_resource_stopped(
                    resource.resource_id,
                    lost=True,
                    error="container missing during reconciliation",
                )
                result["lost"].append(resource.resource_key)
                continue
            if not self._inspection_running(inspection):
                self.docker.force_remove_container(resource.external_id)
                self.store.mark_managed_resource_stopped(resource.resource_id)
                result["stopped"].append(resource.resource_key)
                continue
            writable_bytes = self._writable_bytes(inspection)
            if resource.disk_limit_bytes > 0 and writable_bytes > resource.disk_limit_bytes:
                stopped = self._stop_one(
                    resource,
                    reason=(
                        "container writable layer exceeded limit "
                        f"({writable_bytes} > {resource.disk_limit_bytes} bytes)"
                    ),
                )
                self._merge(result, stopped)
                result["disk_exceeded"].append(resource.resource_key)
        return result

    def close_run(self, run_id: str) -> dict[str, list[str]]:
        """Remove every still-running managed container when a run becomes terminal."""
        resources = self.store.claim_run_resources_for_stop(run_id)
        return self._stop_resources(resources, reason="run settled")

    def serialize(self, resource: ManagedResource) -> dict[str, Any]:
        payload = asdict(resource)
        payload["status"] = str(resource.status)
        return payload

    def describe(self, resource: ManagedResource) -> dict[str, Any]:
        payload = self.serialize(resource)
        target = resource.external_id or resource.name
        inspection = self.docker.inspect_container(target)
        if inspection is None:
            payload["runtime"] = {"running": False, "ports": {}, "writable_layer_bytes": 0}
            return payload
        state = inspection.get("State")
        network = inspection.get("NetworkSettings")
        payload["runtime"] = {
            "running": bool(isinstance(state, dict) and state.get("Running")),
            "ports": network.get("Ports", {}) if isinstance(network, dict) else {},
            "writable_layer_bytes": self._writable_bytes(inspection),
        }
        return payload

    def _stop_resources(
        self, resources: list[ManagedResource], *, reason: str
    ) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {
            "stopped": [],
            "lost": [],
            "disk_exceeded": [],
            "adopted": [],
            "orphaned": [],
            "errors": [],
        }
        seen: set[str] = set()
        for resource in resources:
            if resource.resource_id in seen:
                continue
            seen.add(resource.resource_id)
            self._merge(result, self._stop_one(resource, reason=reason))
        return result

    def _stop_one(self, resource: ManagedResource, *, reason: str) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {
            "stopped": [],
            "lost": [],
            "disk_exceeded": [],
            "adopted": [],
            "orphaned": [],
            "errors": [],
        }
        claimed = self.store.claim_managed_resource_for_stop(resource.resource_id)
        if claimed is None:
            return result
        resource = claimed
        target = resource.external_id or resource.name
        if self.docker.force_remove_container(target):
            self.store.mark_managed_resource_stopped(resource.resource_id, error=reason)
            result["stopped"].append(resource.resource_key)
            return result
        inspection = self.docker.inspect_container(target)
        if inspection is None:
            self.store.mark_managed_resource_stopped(
                resource.resource_id,
                error=f"{reason}; container was already absent during reclamation",
            )
            result["stopped"].append(resource.resource_key)
        else:
            result["errors"].append(
                f"failed to stop {resource.resource_key!r} ({resource.external_id[:12]}): {reason}"
            )
        return result

    def _reconcile_labeled_containers(self, run_id: str) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {
            "stopped": [],
            "lost": [],
            "disk_exceeded": [],
            "adopted": [],
            "orphaned": [],
            "errors": [],
        }
        if not hasattr(self.docker, "list_managed_containers"):
            return result
        tracked = {
            resource.resource_id: resource
            for resource in self.store.list_managed_resources(run_id)
            if resource.status
            in (ResourceStatus.PREPARING, ResourceStatus.RUNNING, ResourceStatus.STOPPING)
        }
        for container_id in self.docker.list_managed_containers(run_id):
            inspection = self.docker.inspect_container(container_id)
            config = inspection.get("Config") if isinstance(inspection, dict) else None
            labels = config.get("Labels") if isinstance(config, dict) else None
            resource_id = labels.get("drostpp.resource_id") if isinstance(labels, dict) else None
            resource = tracked.get(str(resource_id)) if resource_id else None
            if resource is not None:
                if resource.status == ResourceStatus.PREPARING:
                    adopted = self.store.adopt_prepared_resource(
                        resource.resource_id, container_id
                    )
                    if adopted is not None:
                        result["adopted"].append(adopted.resource_key)
                continue
            if self.docker.force_remove_container(container_id):
                result["orphaned"].append(container_id[:12])
            else:
                result["errors"].append(
                    f"failed to remove untracked Drost++ container {container_id[:12]}"
                )
        return result

    @staticmethod
    def _merge(target: dict[str, list[str]], source: dict[str, list[str]]) -> None:
        for key, values in source.items():
            target.setdefault(key, []).extend(values)

    @staticmethod
    def _inspection_running(inspection: dict[str, object] | None) -> bool:
        if inspection is None:
            return False
        state = inspection.get("State")
        return bool(isinstance(state, dict) and state.get("Running"))

    @staticmethod
    def _writable_bytes(inspection: dict[str, object]) -> int:
        try:
            return max(0, int(inspection.get("SizeRw") or 0))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _validated_key(resource_key: str) -> str:
        key = resource_key.strip()
        if not _RESOURCE_KEY_RE.fullmatch(key):
            raise ValueError(
                "resource key must be 1-80 characters: letters, numbers, dot, underscore, dash"
            )
        return key

    @staticmethod
    def _container_name(run_id: str, resource_key: str) -> str:
        safe_key = re.sub(r"[^a-z0-9_.-]+", "-", resource_key.lower()).strip("-.")
        digest = hashlib.sha256(f"{run_id}\0{resource_key}".encode()).hexdigest()[:8]
        return f"dpp-{run_id[-8:].lower()}-{safe_key[:32]}-{digest}"[:63]

    def _check_host_admission(self, run_id: str) -> None:
        owned_resources = [
            resource
            for resource in self.store.list_managed_resources(run_id)
            if resource.status
            in (ResourceStatus.PREPARING, ResourceStatus.RUNNING, ResourceStatus.STOPPING)
        ]
        reserved_task_memory_mb = 0
        for attempt in self.store.list_attempts(run_id):
            if attempt.status not in (AttemptStatus.STARTING, AttemptStatus.RUNNING):
                continue
            task = self.store.get_task(attempt.task_id)
            if task is None:
                continue
            try:
                reserved_task_memory_mb += TaskBudget.from_dict(
                    json.loads(task.budget_json)
                ).max_memory_mb
            except (json.JSONDecodeError, TypeError, ValueError):
                reserved_task_memory_mb += self.config.memory_mb

        if self.min_available_memory_mb > 0 or self.config.memory_mb > 0:
            try:
                values = {
                    line.split(":", 1)[0]: int(line.split()[1])
                    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines()
                    if ":" in line
                }
                available_mb = values["MemAvailable"] // 1024
                total_mb = values["MemTotal"] // 1024
            except (OSError, KeyError, ValueError, IndexError):
                available_mb = self.min_available_memory_mb + self.config.memory_mb
                total_mb = (
                    self.min_available_memory_mb
                    + reserved_task_memory_mb
                    + sum(resource.memory_limit_mb for resource in owned_resources)
                    + self.config.memory_mb
                )
            immediate_required_mb = self.min_available_memory_mb + self.config.memory_mb
            reserved_required_mb = (
                self.min_available_memory_mb
                + reserved_task_memory_mb
                + sum(resource.memory_limit_mb for resource in owned_resources)
                + self.config.memory_mb
            )
            if available_mb < immediate_required_mb:
                raise BudgetExceededError(
                    "managed container admission would breach host memory floor "
                    f"({available_mb} MiB available < {immediate_required_mb} MiB required)"
                )
            if total_mb < reserved_required_mb:
                raise BudgetExceededError(
                    "managed container caps overcommit host memory "
                    f"({reserved_required_mb} MiB reserved > {total_mb} MiB total)"
                )

        if self.min_free_disk_bytes > 0 or self.config.disk_limit_bytes > 0:
            root = self.docker.docker_root_dir() if hasattr(self.docker, "docker_root_dir") else None
            check_path = root if root is not None and root.exists() else self.store.db_path.parent
            try:
                free_bytes = shutil.disk_usage(check_path).free
            except OSError:
                free_bytes = self.min_free_disk_bytes + self.config.disk_limit_bytes
            required_bytes = (
                self.min_free_disk_bytes
                + sum(resource.disk_limit_bytes for resource in owned_resources)
                + self.config.disk_limit_bytes
            )
            if free_bytes < required_bytes:
                raise BudgetExceededError(
                    "managed container admission would breach host disk floor "
                    f"({free_bytes} available < {required_bytes} bytes required)"
                )
