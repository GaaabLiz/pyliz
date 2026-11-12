#!/usr/bin/env python3
"""Run the snapshot E2E suite in a unique ``test_local`` workspace."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
E2E_TEST_DIRECTORY = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser(description="Run real-filesystem E2E scenarios for snapshot operations.")
    parser.add_argument(
        "--root",
        type=Path,
        default=REPOSITORY_ROOT / "test_local",
        help="Parent directory for this run's private workspace (default: ./test_local).",
    )
    parser.add_argument("--keep", action="store_true", help="Keep the run workspace after successful tests.")
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER, help="Additional pytest arguments after --.")
    args = parser.parse_args()

    run_parent = args.root.expanduser().resolve() / "snapshot_e2e"
    run_parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_root = run_parent / f"run-{stamp}-{uuid.uuid4().hex[:8]}"
    run_root.mkdir()

    environment = os.environ.copy()
    environment["PYLIZ_SNAPSHOT_E2E_RUN_ROOT"] = str(run_root)
    environment["PYLIZ_SNAPSHOT_E2E_KEEP"] = "1" if args.keep else "0"
    sys.path.insert(0, str(REPOSITORY_ROOT))

    print(f"Snapshot E2E workspace: {run_root}", flush=True)
    try:
        import pytest

        pytest_args = [str(E2E_TEST_DIRECTORY), "-v", *args.pytest_args]
        previous_environment = os.environ.copy()
        os.environ.update(environment)
        try:
            exit_code = int(pytest.main(pytest_args))
        finally:
            os.environ.clear()
            os.environ.update(previous_environment)
    except KeyboardInterrupt:
        print(f"Interrupted; workspace retained at {run_root}", file=sys.stderr)
        return 130

    if exit_code == 0 and not args.keep:
        shutil.rmtree(run_root)
        print("E2E passed; its private workspace was removed.")
    else:
        print(f"Workspace retained at {run_root}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
