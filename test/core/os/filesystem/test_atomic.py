"""Protected atomic publication works without snapshot model dependencies."""

import pytest

from pylizlib.core.os.filesystem.atomic import AtomicFile, FileDurabilityError
from pylizlib.core.os.filesystem.entries import entry_exists, remove_entry


def test_general_atomic_file_preserves_previous_bytes(tmp_path):
    """Publication handles arbitrary binary data and the immediately previous version."""
    path = tmp_path / "binary"
    AtomicFile.write_bytes(path, b"\x00old")
    AtomicFile.write_bytes(path, b"\x00new")
    assert AtomicFile.read_bytes(path) == b"\x00new"
    assert AtomicFile.read_bytes(AtomicFile.previous_path(path)) == b"\x00old"
    with pytest.raises(TypeError, match="File contents must be bytes"):
        AtomicFile.write_bytes(path, "text")


def test_general_atomic_file_reports_post_publication_failure(tmp_path, monkeypatch):
    """A failed final flush must not be mistaken for an unpublished version."""
    path = tmp_path / "binary"

    def failed_sync(path, expected_parent):
        """Fail after the new file has become visible."""
        raise OSError("flush failed")

    monkeypatch.setattr(AtomicFile, "_sync_parent_directory", failed_sync)
    with pytest.raises(FileDurabilityError) as error:
        AtomicFile.write_bytes(path, b"new")
    assert error.value.published is True
    assert error.value.durability_confirmed is False
    assert error.value.path == path
    assert path.read_bytes() == b"new"
    assert not list(tmp_path.glob(".*.tmp"))


def test_entry_removal_does_not_follow_dangling_links(tmp_path):
    """An absent target does not hide a link that recovery still needs to remove."""
    link = tmp_path / "dangling"
    try:
        link.symlink_to(tmp_path / "absent")
    except OSError as error:
        pytest.skip(f"symlink creation unavailable: {error}")
    assert entry_exists(link)
    remove_entry(link)
    assert not entry_exists(link)
    assert remove_entry(link) is None
