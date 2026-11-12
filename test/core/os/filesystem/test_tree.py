"""Verify general tree primitives independently of snapshot models."""

import subprocess
import sys

import pytest

from pylizlib.core.os.filesystem.tree import assert_no_symlinks, iter_files_strict, iter_tree_entries_strict
from pylizlib.core.os.paths.containment import assert_destination_outside_source
from pylizlib.core.os.paths.identity import same_filesystem_entry


def test_tree_preserves_empty_directories_and_omits_root(tmp_path):
    """File and entry enumeration share the same strict traversal policy."""
    (tmp_path / "empty").mkdir()
    (tmp_path / "file").write_bytes(b"content")
    assert set(iter_tree_entries_strict(tmp_path)) == {tmp_path / "empty", tmp_path / "file"}
    assert list(iter_files_strict(tmp_path)) == [tmp_path / "file"]
    assert assert_no_symlinks(tmp_path) is None


def test_recursive_copy_and_filesystem_aliases(tmp_path):
    """Containment follows aliases; identity does not require lexical equality."""
    with pytest.raises(ValueError, match="inside source"):
        assert_destination_outside_source(tmp_path, tmp_path / "child")
    file = tmp_path / "file"
    file.touch()
    alias = tmp_path / "alias"
    alias.hardlink_to(file)
    assert same_filesystem_entry(file, alias)


def test_general_primitives_import_without_snapshot_dependencies():
    """Reusable filesystem imports must not load the snapshot package."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import pylizlib.core.os.filesystem.tree; import pylizlib.core.os.paths.identity; assert not any(name.startswith('pylizlib.core.os.snap') for name in sys.modules)",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
