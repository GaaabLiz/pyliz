"""Protected atomic publication works without snapshot model dependencies."""

import stat

import pytest

from pylizlib.core.os.filesystem.atomic import AtomicFile, FileDurabilityError
from pylizlib.core.os.filesystem.entries import entry_exists, remove_entry


def test_atomic_file_uses_the_protected_opener_for_reads_and_staging(tmp_path):
    """Hooks receive descriptor flags and preserve the old mode for both versions."""
    path = tmp_path / "binary"
    path.write_bytes(b"old")
    original_mode = stat.S_IMODE(path.stat().st_mode)
    calls = []

    def tracked_open(path, flags, mode=0o666):
        """Keep protected opening while retaining the hook's positional contract."""
        calls.append((path, flags, mode))
        return AtomicFile.open_file(path, flags, mode)

    AtomicFile.write_bytes(path, b"new", opener=tracked_open)
    assert AtomicFile.read_bytes(path, opener=tracked_open) == b"new"
    assert AtomicFile.previous_path(path).read_bytes() == b"old"
    assert calls[0][0] == path and calls[-1][0] == path
    staging_modes = [mode for entry, _, mode in calls if entry != path]
    assert staging_modes == [original_mode, original_mode]


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


def test_atomic_write_rejects_a_concurrently_changed_previous_version(tmp_path, monkeypatch):
    """Previous-version inspection must finish before any staging file is created."""
    path = tmp_path / "target"
    path.write_bytes(b"old")
    read = AtomicFile.read_bytes

    def read_then_change(path, opener=None):
        """Simulate an external writer changing the file between read and recheck."""
        contents = read(path, opener=opener)
        path.write_bytes(b"concurrent version")
        return contents

    monkeypatch.setattr(AtomicFile, "read_bytes", read_then_change)
    with pytest.raises(OSError, match="changed while preparing"):
        AtomicFile.write_bytes(path, b"requested")
    assert path.read_bytes() == b"concurrent version"
    assert not AtomicFile.previous_path(path).exists()
    assert not list(tmp_path.glob(".*.tmp"))
