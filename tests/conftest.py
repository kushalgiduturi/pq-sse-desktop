"""Shared pytest fixtures."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pqsse.pqbackend import FAST_PARAMS  # noqa: E402


@pytest.fixture(scope="session")
def params():
    """Smallest parameter set, used by the bulk randomized tests (see PLAN.md D16)."""
    return FAST_PARAMS


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    """Never touch the real %LOCALAPPDATA% folder from tests."""
    monkeypatch.setenv("PQSSE_DATA_DIR", str(tmp_path / "data"))
    yield
    from pqsse import paths

    paths.set_profile("")
