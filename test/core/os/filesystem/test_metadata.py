"""General metadata and fingerprints retain topology and ordering guarantees."""

import os
import shutil

import pytest

from pylizlib.core.os.filesystem.fingerprints import fingerprint_tree
from pylizlib.core.os.filesystem.metadata import TreeMetadataCopier, copy_extended_attributes


@pytest.mark.parametrize("missing", ["listxattr", "getxattr", "setxattr"])
def test_extended_attributes_require_all_three_runtime_functions(tmp_path, monkeypatch, missing):
    """Missing xattr capability performs no partial attribute read or write."""
    calls = []
    for name in ("listxattr", "getxattr", "setxattr"):
        monkeypatch.setattr(os, name, None if name == missing else lambda *args, **kwargs: calls.append(args), raising=False)
    assert copy_extended_attributes(tmp_path / "source", tmp_path / "destination") is None
    assert calls == []


def test_metadata_recreates_hardlinks_and_orders_platform_backends(tmp_path, monkeypatch):
    """Ownership precedes stat/xattr; Windows ACLs follow all other metadata work."""
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    (source / "first").write_bytes(b"content")
    (source / "second").hardlink_to(source / "first")
    shutil.copytree(source, destination)
    events = []
    copy_stat = shutil.copystat

    def stat_then_record(first, second, **kwargs):
        """Retain actual stat copying while observing backend order."""
        events.append(("stat", second))
        return copy_stat(first, second, **kwargs)

    monkeypatch.setattr(shutil, "copystat", stat_then_record)
    copier = TreeMetadataCopier(
        owner_group=lambda first, second: events.append(("owner", second)),
        attributes=lambda first, second: events.append(("xattr", second)),
        windows_streams=lambda first, second: events.append(("streams", second)),
        windows_security=lambda first, second: events.append(("security", second)),
    )
    copier.preserve(source, destination)
    assert (destination / "first").samefile(destination / "second")
    if os.name == "nt":
        kinds = [kind for kind, _ in events]
        first_security = kinds.index("security")
        assert all(kind == "security" for kind in kinds[first_security:])
        assert "streams" in kinds[:first_security]
    else:
        for target in {target for _, target in events}:
            assert [kind for kind, path in events if path == target] == ["owner", "stat", "xattr"]


def test_fingerprint_detects_same_size_changes_and_empty_directories(tmp_path):
    """Content hashes distinguish equal-size writes and preserve directory presence."""
    (tmp_path / "empty").mkdir()
    (tmp_path / "file").write_bytes(b"first")
    before = fingerprint_tree(tmp_path)
    assert before["."] == ("directory", 0)
    assert before["empty"] == ("directory", 0)
    assert before["file"][1] == 5
    (tmp_path / "file").write_bytes(b"other")
    assert fingerprint_tree(tmp_path)["file"] != before["file"]


def test_metadata_failure_propagates_without_removing_caller_owned_tree(tmp_path):
    """Metadata orchestration owns no staging cleanup; the copy coordinator does."""
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    destination.mkdir()
    original = OSError("metadata unavailable")

    def failed_backend(source, destination):
        """Fail the platform-selected inode metadata phase."""
        raise original

    copier = TreeMetadataCopier(owner_group=failed_backend, windows_streams=failed_backend)
    with pytest.raises(OSError) as error:
        copier.preserve(source, destination)
    assert error.value is original
    assert destination.is_dir()
