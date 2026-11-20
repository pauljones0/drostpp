"""Run/task budget enforcement, disk accounting, and repeated-error stall normalization."""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil

from .models import BudgetExceededError, ErrorKind, RunBudget, RunRecord
from .store import parse_iso, utc_now

_HEX_RE = re.compile(r"\b[0-9a-fA-F]{6,}\b")
_NUM_RE = re.compile(r"\b\d+\b")
_WS_RE = re.compile(r"\s+")


def compute_dir_bytes(path: Path | str) -> int:
    """Safely sum regular file sizes under path without following symlinks or failing on dangling links."""
    root = Path(path)
    if not root.exists():
        return 0
    if root.is_symlink():
        return 0
    if root.is_file():
        try:
            return root.stat(follow_symlinks=False).st_size
        except OSError:
            return 0

    total = 0
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_file(follow_symlinks=False):
                            total += entry.stat(follow_symlinks=False).st_size
                        elif entry.is_dir(follow_symlinks=False):
                            stack.append(Path(entry.path))
                    except OSError:
                        continue
        except OSError:
            continue
    return total


def error_signature(error_kind: ErrorKind | str, message: str | None) -> str:
    """Normalize volatile tokens/numbers out of an error string for stall detection."""
    raw = (message or "").strip().lower()
    raw = _HEX_RE.sub("<hex>", raw)
    raw = _NUM_RE.sub("<n>", raw)
    raw = _WS_RE.sub(" ", raw)[:240]
    return f"{str(error_kind).lower()}:{raw}"


class BudgetTracker:
    """Checks run-level token, wall-time, workspace disk usage, and host free disk limits."""

    def __init__(self, run_budget: RunBudget) -> None:
        self.run_budget = run_budget

    def check_run_admission(self, run: RunRecord, state_dir: Path) -> int:
        """Validate run budgets before claiming new work. Returns current disk usage bytes."""
        if run.tokens_used >= self.run_budget.max_tokens:
            raise BudgetExceededError(
                f"run token budget exhausted ({run.tokens_used} >= {self.run_budget.max_tokens})"
            )

        elapsed = (utc_now() - parse_iso(run.created_at)).total_seconds()
        if elapsed >= self.run_budget.max_wall_seconds:
            raise BudgetExceededError(
                f"run wall budget exhausted ({elapsed:.1f}s >= {self.run_budget.max_wall_seconds:.1f}s)"
            )

        disk_bytes = compute_dir_bytes(state_dir)
        if disk_bytes >= self.run_budget.max_disk_bytes:
            raise BudgetExceededError(
                f"run disk budget exhausted ({disk_bytes} >= {self.run_budget.max_disk_bytes} bytes)"
            )

        if self.run_budget.min_free_disk_bytes > 0:
            check_path = state_dir if state_dir.exists() else state_dir.parent
            try:
                free_bytes = shutil.disk_usage(check_path).free
            except OSError:
                free_bytes = self.run_budget.min_free_disk_bytes
            if free_bytes < self.run_budget.min_free_disk_bytes:
                raise BudgetExceededError(
                    f"host free disk below safety floor ({free_bytes} < {self.run_budget.min_free_disk_bytes} bytes)"
                )

        return disk_bytes
