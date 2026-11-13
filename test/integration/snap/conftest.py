"""Isolated workspaces for snapshot integration scenarios."""

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
    """Create one isolated workspace under test_local or a runner-selected root.

    Snapshot install and restore intentionally reject OS-managed temporary
    directories as destructive targets, so normal runs use a unique child of
    the repository's test_local directory. Only the exact workspace created
    for this test is removed.
    """
    run_root_value = os.environ.get("PYLIZ_SNAPSHOT_INTEGRATION_RUN_ROOT")
    run_root = Path(run_root_value).resolve() if run_root_value else (REPOSITORY_ROOT / "test_local" / "snapshot_integration").resolve()
    run_root.mkdir(parents=True, exist_ok=True)

    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", request.node.name).strip("_.") or "scenario"
    workspace = Path(tempfile.mkdtemp(prefix=f"{safe_name}-", dir=run_root))
    yield workspace

    report = getattr(request.node, "rep_call", None)
    failed = report is not None and report.failed
    keep = os.environ.get("PYLIZ_SNAPSHOT_INTEGRATION_KEEP") == "1"
    if failed or keep:
        print(f"Snapshot integration workspace retained: {workspace}")
    else:
        shutil.rmtree(workspace)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[object]):
    """Expose the call result to the workspace fixture for failure retention."""
    outcome = yield
    setattr(item, f"rep_{call.when}", outcome.get_result())
