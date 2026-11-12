"""Isolated workspaces for real-filesystem snapshot E2E scenarios."""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def snapshot_workspace(request: pytest.FixtureRequest) -> Path:
    """Create one private scenario directory under the configured test root.

    The fixture only removes the exact directory it created. Failed scenarios
    are retained for inspection; successful ones are removed unless the runner
    was started with ``--keep``.
    """
    run_root_value = os.environ.get("PYLIZ_SNAPSHOT_E2E_RUN_ROOT")
    if run_root_value:
        run_root = Path(run_root_value).resolve()
        run_root.mkdir(parents=True, exist_ok=True)
    else:
        configured_root = Path(os.environ.get("PYLIZ_SNAPSHOT_E2E_ROOT", REPOSITORY_ROOT / "test_local")).resolve()
        run_root = configured_root / "snapshot_e2e"
        run_root.mkdir(parents=True, exist_ok=True)

    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", request.node.name).strip("_.") or "scenario"
    workspace = Path(tempfile.mkdtemp(prefix=f"{safe_name}-", dir=run_root))
    yield workspace

    report = getattr(request.node, "rep_call", None)
    failed = report is not None and report.failed
    keep = os.environ.get("PYLIZ_SNAPSHOT_E2E_KEEP") == "1"
    if failed or keep:
        print(f"Snapshot E2E workspace retained: {workspace}")
    else:
        shutil.rmtree(workspace)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[object]):
    """Expose the call result to the workspace fixture for failure retention."""
    outcome = yield
    setattr(item, f"rep_{call.when}", outcome.get_result())
