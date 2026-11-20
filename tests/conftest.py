"""Shared fixtures for offline drost++ tests."""

from __future__ import annotations

from pathlib import Path
import sys
import pytest

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


@pytest.fixture()
def state_dir(tmp_path: Path) -> Path:
    d = tmp_path / "state"
    d.mkdir(parents=True, exist_ok=True)
    return d
