"""External bridge for Drost Community Edition (MCP config, health self-test, and workspace sync)."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
from pathlib import Path
import re
from typing import Any
import uuid

from ..blackboard import Blackboard
from ..config import DrostConfig
from ..models import ArtifactRecord, BlackboardKind, BudgetExceededError, McpServerConfig
from ..store import SQLiteStore
from ..supervision import ProcessSupervisor

ENGAGEMENT_ID_RE = re.compile(r"^eng_\d{8}_[0-9a-f]{32}$")
_IMPORT_SUBDIRS = ("artifacts", "evidence", "findings")


def validate_engagement_id(engagement_id: str) -> str:
    if not isinstance(engagement_id, str) or not ENGAGEMENT_ID_RE.fullmatch(engagement_id):
        raise ValueError(
            f"invalid Drost engagement_id {engagement_id!r}; expected eng_YYYYMMDD_<32-hex>"
        )
    return engagement_id


def build_drost_mcp_config(cfg: DrostConfig) -> McpServerConfig:
    """Build an McpServerConfig targeting Drost inside its container via `docker exec -i`."""
    mode = cfg.mcp_mode.strip().lower()
    if mode not in {"compact", "full"}:
        raise ValueError(f"unsupported drost.mcp_mode: {cfg.mcp_mode!r}")

    env_map: dict[str, str] = {"DROST_MCP_MODE": mode}
    if cfg.tool_categories:
        env_map["DROST_TOOL_CATEGORIES"] = ",".join(cfg.tool_categories)
    env_map.update(cfg.extra_env)

    args = ["exec", "-i"]
    for key in sorted(env_map):
        args.extend(["-e", f"{key}={env_map[key]}"])
    args.extend([cfg.container_name, cfg.mcp_command])

    return McpServerConfig(
        name="drost",
        command=cfg.docker_binary,
        args=args,
        env={},
        timeout_seconds=120.0,
        max_result_bytes=256 * 1024,
        enabled=cfg.enabled,
    )


def check_drost_health(
    cfg: DrostConfig,
    *,
    timeout_seconds: float = 15.0,
    supervisor: ProcessSupervisor | None = None,
) -> dict[str, Any]:
    """Run `drost-mcp --self-test` inside the configured container and require both exit=0 and clean JSON."""
    sup = supervisor or ProcessSupervisor()
    argv = [cfg.docker_binary, "exec", cfg.container_name, cfg.mcp_command, "--self-test"]
    try:
        res = sup.run(argv, wall_timeout=timeout_seconds, max_output_bytes=512 * 1024)
    except OSError as exc:
        return {
            "healthy": False,
            "exit_code": -1,
            "error": str(exc),
            "missing_executables": [],
            "raw": {},
        }

    parsed: dict[str, Any] = {}
    parse_error: str | None = None
    if res.stdout.strip():
        try:
            loaded = json.loads(res.stdout)
            if isinstance(loaded, dict):
                parsed = loaded
            else:
                parse_error = "self-test output was not a JSON object"
        except json.JSONDecodeError as exc:
            parse_error = f"invalid self-test JSON: {exc}"
    else:
        parse_error = "empty self-test stdout"

    missing = parsed.get("missing_executables")
    if not isinstance(missing, list):
        missing = []
    status_ok = parsed.get("status") == "healthy"
    # Explicitly require exit_code == 0 AND healthy status AND no missing executables.
    healthy = (
        res.returncode == 0
        and not res.timed_out
        and status_ok
        and len(missing) == 0
        and parse_error is None
    )
    return {
        "healthy": healthy,
        "exit_code": res.returncode,
        "timed_out": res.timed_out,
        "status": parsed.get("status"),
        "missing_executables": missing,
        "parse_error": parse_error,
        "stderr": res.stderr.strip(),
        "raw": parsed,
    }


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON atomically using a unique per-writer staging file to avoid cross-process collisions."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    data = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    fd = os.open(tmp, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o644)
    try:
        os.write(fd, data)
        os.fsync(fd)
    except BaseException:
        os.close(fd)
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    os.close(fd)
    os.replace(tmp, path)


class DrostWorkspaceBridge:
    """Defensive host-side reader and artifact importer for Drost engagement workspaces."""

    def __init__(self, workspace_root: Path | str) -> None:
        self.workspace_root = Path(workspace_root).resolve()

    @property
    def engagements_root(self) -> Path:
        return self.workspace_root / "engagements"

    def _resolve_engagement_dir(self, engagement_id: str) -> Path:
        validate_engagement_id(engagement_id)
        root = self.engagements_root.resolve()
        candidate = root / engagement_id
        if candidate.is_symlink():
            raise ValueError(f"engagement directory must not be a symlink: {engagement_id}")
        resolved = candidate.resolve()
        if resolved != root / engagement_id:
            raise ValueError(f"engagement path escaped workspace root: {engagement_id}")
        if not resolved.is_dir():
            raise ValueError(f"unknown engagement_id: {engagement_id}")
        return resolved

    def _load_manifest_safe(self, engagement_id: str) -> dict[str, Any]:
        eng_dir = self._resolve_engagement_dir(engagement_id)
        manifest_path = eng_dir / "engagement.json"
        if manifest_path.is_symlink() or not manifest_path.is_file():
            raise ValueError(f"missing engagement manifest: {engagement_id}")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid engagement manifest JSON: {exc}") from exc
        if not isinstance(manifest, dict) or manifest.get("engagement_id") != engagement_id:
            raise ValueError(f"mismatched engagement_id in manifest: {engagement_id}")
        created_at = manifest.get("created_at")
        if not isinstance(created_at, str) or not created_at.strip():
            raise ValueError(f"manifest missing valid created_at timestamp: {engagement_id}")
        targets = manifest.get("targets")
        if not isinstance(targets, list):
            raise ValueError(f"manifest missing valid targets list: {engagement_id}")
        return {
            **manifest,
            "workspace": str(eng_dir),
        }

    def list_engagements(self) -> dict[str, Any]:
        root = self.engagements_root
        if not root.is_dir():
            return {
                "workspace": str(self.workspace_root),
                "engagements": [],
                "invalid_engagements": [],
            }
        valid: list[dict[str, Any]] = []
        invalid: list[dict[str, str]] = []
        for entry in sorted(root.iterdir()):
            if entry.is_symlink() or not entry.is_dir() or not ENGAGEMENT_ID_RE.fullmatch(entry.name):
                continue
            try:
                valid.append(self._load_manifest_safe(entry.name))
            except ValueError as exc:
                invalid.append({"engagement_id": entry.name, "error": str(exc)})
        valid.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
        return {
            "workspace": str(self.workspace_root),
            "engagements": valid,
            "invalid_engagements": invalid,
        }

    def get_engagement(self, engagement_id: str) -> dict[str, Any]:
        return self._load_manifest_safe(engagement_id)

    def sync_engagement_to_run(
        self,
        store: SQLiteStore,
        blackboard: Blackboard,
        *,
        run_id: str,
        engagement_id: str,
        artifact_store_dir: Path,
        max_import_bytes: int = 32 * 1024 * 1024,
    ) -> dict[str, Any]:
        """Import artifacts/evidence/findings files into the content-addressed store & Blackboard."""
        eng_dir = self._resolve_engagement_dir(engagement_id)
        artifact_store_dir.mkdir(parents=True, exist_ok=True)

        existing = store.list_artifacts(run_id)
        known_hashes = {a.sha256 for a in existing}
        imported_bytes = sum(a.size_bytes for a in existing)

        imported: list[ArtifactRecord] = []
        skipped_duplicates = 0
        skipped_symlinks = 0

        for subdir_name in _IMPORT_SUBDIRS:
            subdir = eng_dir / subdir_name
            if not subdir.exists() or subdir.is_symlink() or not subdir.is_dir():
                continue
            stack = [subdir]
            while stack:
                current = stack.pop()
                try:
                    entries = sorted(os.scandir(current), key=lambda e: e.name)
                except OSError:
                    continue
                for entry in entries:
                    try:
                        if entry.is_symlink():
                            skipped_symlinks += 1
                            continue
                        entry_path = Path(entry.path)
                        resolved = entry_path.resolve()
                        if eng_dir not in resolved.parents:
                            skipped_symlinks += 1
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry_path)
                            continue
                        if not entry.is_file(follow_symlinks=False):
                            continue
                        stat_res = entry.stat(follow_symlinks=False)
                        if imported_bytes + stat_res.st_size > max_import_bytes:
                            raise BudgetExceededError(
                                f"Drost artifact import cap exceeded ({imported_bytes + stat_res.st_size} > {max_import_bytes} bytes)"
                            )
                        digest, size = _hash_and_copy(entry_path, artifact_store_dir)
                        if digest in known_hashes:
                            skipped_duplicates += 1
                            continue
                        rel_from_eng = str(entry_path.relative_to(eng_dir))
                        media_type, _ = mimetypes.guess_type(entry_path.name)
                        record, dedup = store.record_artifact(
                            run_id,
                            digest,
                            f"{digest[:2]}/{digest}",
                            size,
                            source_path=str(entry_path),
                            media_type=media_type or "application/octet-stream",
                            metadata={"engagement_id": engagement_id, "engagement_rel": rel_from_eng},
                        )
                        if not dedup:
                            known_hashes.add(digest)
                            imported_bytes += size
                            imported.append(record)
                            blackboard.publish(
                                run_id,
                                BlackboardKind.ARTIFACT_REF,
                                f"Drost artifact: {rel_from_eng}",
                                f"sha256={digest} size={size} bytes (engagement={engagement_id})",
                                tags=["drost", subdir_name],
                                confidence=1.0,
                            )
                    except OSError:
                        continue

        return {
            "engagement_id": engagement_id,
            "imported_count": len(imported),
            "skipped_duplicates": skipped_duplicates,
            "skipped_symlinks": skipped_symlinks,
            "total_artifact_bytes": imported_bytes,
            "artifacts": [a.rel_path for a in imported],
        }


def _hash_and_copy(src: Path, store_dir: Path) -> tuple[str, int]:
    hasher = hashlib.sha256()
    total = 0
    with src.open("rb") as fp:
        while True:
            chunk = fp.read(65536)
            if not chunk:
                break
            hasher.update(chunk)
            total += len(chunk)
    digest = hasher.hexdigest()
    dst_dir = store_dir / digest[:2]
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / digest
    if not dst.exists():
        tmp = dst_dir / f".{digest}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
        try:
            with src.open("rb") as src_fp, tmp.open("wb") as dst_fp:
                while True:
                    chunk = src_fp.read(65536)
                    if not chunk:
                        break
                    dst_fp.write(chunk)
                dst_fp.flush()
                os.fsync(dst_fp.fileno())
            os.replace(tmp, dst)
        finally:
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass
    return digest, total
