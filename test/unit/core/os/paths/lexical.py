"""General lexical path normalization and mapping adapter contracts."""

from pathlib import PureWindowsPath

import pytest

from pylizlib.core.os.paths import lexical


def test_foreign_absolute_paths_do_not_query_the_filesystem():
    """Windows and POSIX roots remain recognizable on every host."""
    assert lexical.is_absolute_path(r"\\server\share\folder")
    assert lexical.is_absolute_path("/source")
    assert lexical.normalize_rooted_path(r"\\server\share\folder") == "//server/share/folder"


def test_mapping_preserves_parent_components_and_translates_errors():
    """A mapping lookup changes the root, without resolving the lexical suffix."""
    path = PureWindowsPath(r"Z:\alias\..\data")
    assert lexical.normalize_mapped_drive(path, unc_root=lambda drive: r"\\host\share") == "//host/share/alias/../data"

    def unavailable(drive):
        """Simulate an unavailable mapping in a different logon context."""
        raise OSError("mapping unavailable")

    with pytest.raises(ValueError, match="Use the UNC path directly") as error:
        lexical.normalize_mapped_drive(path, unc_root=unavailable)
    assert isinstance(error.value.__cause__, OSError)


def test_general_validation_labels_and_anchoring(tmp_path, monkeypatch):
    """The general API has no snapshot-specific validation messages."""
    monkeypatch.chdir(tmp_path)
    assert lexical.normalize_rooted_path("child/../data") == (tmp_path / "child/../data").as_posix()
    with pytest.raises(TypeError, match="Path must be a string"):
        lexical.normalize_rooted_path(None)
    with pytest.raises(ValueError, match="Path must be absolute"):
        lexical.normalize_rooted_path("relative", allow_relative=False)
