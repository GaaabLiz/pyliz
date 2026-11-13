"""Exercise documentation commands and rendering with the declared dev tools."""

import shlex
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("target", ["docs", "docs-snap"])
def test_make_documentation_uses_declared_group_and_google_renderer(target):
    """The actual Make recipe selects an installed pdoc group and matching style."""
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())
    result = subprocess.run(["make", "--no-print-directory", "-n", target], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    command = shlex.split(result.stdout.replace("\\\n", " "))
    group = command[command.index("--group") + 1]
    assert any(requirement.startswith("pdoc") for requirement in config["dependency-groups"][group])
    assert command[command.index("-d") + 1] == "google"
    assert (ROOT / config["project"]["readme"]).is_file()


def test_public_snapshot_docs_render_new_contracts(tmp_path):
    """pdoc renders public fields, result types and post-commit error semantics."""
    result = subprocess.run([sys.executable, "-m", "pdoc", "--no-show-source", "-d", "google", "-o", str(tmp_path), "pylizlib.core.os.snap"], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert not result.stderr, result.stderr
    html = (tmp_path / "pylizlib/core/os/snap.html").read_text()
    for public_symbol in ("ExtendedMetadataCopyStrategy", "SnapshotInstallMetadataError", "SnapshotSearchParams", "SnapshotSettings", "SnapshotBusyError"):
        assert f'id="{public_symbol}"' in html
    for documented_term in ("max_context_chars", "metadata_published", "capture_started_at", "Arguments:", "Returns:"):
        assert documented_term in html
