"""Atomic metadata publication and recovery-sidecar regressions."""

import json

import pytest

from pylizlib.core.os.snap.catalogue import SnapshotCatalogue
from pylizlib.core.os.snap.domain import Snapshot
from pylizlib.core.os.snap.manager import SnapshotManager
from pylizlib.core.os.snap.serializer import SnapshotSerializer
from pylizlib.core.os.snap.storage.metadata import MetadataDurabilityError, MetadataFile


def test_interrupted_temp_write_leaves_previous_json_and_cleans_staging(tmp_path, monkeypatch):
    """A partial temporary write never truncates the currently published JSON."""
    metadata_path = tmp_path / "snapshot.json"
    SnapshotSerializer.to_json(Snapshot("id", "before", ""), metadata_path)
    previous_bytes = metadata_path.read_bytes()
    real_write_temporary = MetadataFile._write_temporary

    def interrupt_after_partial_write(path, contents, opener, mode, *, preserve_mode):
        """Persist only a prefix in staging, then simulate process/write failure."""
        real_write_temporary(path, contents[: max(1, len(contents) // 3)], opener, mode, preserve_mode=preserve_mode)
        raise OSError("simulated interrupted metadata write")

    monkeypatch.setattr(MetadataFile, "_write_temporary", interrupt_after_partial_write)
    with pytest.raises(OSError, match="interrupted metadata write"):
        SnapshotSerializer.to_json(Snapshot("id", "after", ""), metadata_path)

    assert metadata_path.read_bytes() == previous_bytes
    assert SnapshotSerializer.from_json(metadata_path).name == "before"
    assert not list(tmp_path.glob("*.tmp"))
    assert not list(tmp_path.glob(".*.tmp"))
    assert not MetadataFile.previous_path(metadata_path).exists()


def test_catalogue_keeps_snapshot_visible_after_interrupted_json_write(tmp_path, monkeypatch):
    """An interrupted metadata update leaves get_all reading the old version."""
    snapshot = Snapshot("visible", "before", "")
    manager = SnapshotManager(snapshot, tmp_path / "catalogue")
    manager.create()
    real_write_temporary = MetadataFile._write_temporary

    def interrupt_after_partial_write(path, contents, opener, mode, *, preserve_mode):
        """Leave a partial staging file but fail before the JSON name changes."""
        real_write_temporary(path, contents[: max(1, len(contents) // 3)], opener, mode, preserve_mode=preserve_mode)
        raise OSError("simulated metadata interruption")

    monkeypatch.setattr(MetadataFile, "_write_temporary", interrupt_after_partial_write)
    with pytest.raises(OSError, match="metadata interruption"):
        SnapshotSerializer.to_json(Snapshot("visible", "after", ""), manager.path_snapshot_json)

    loaded = SnapshotCatalogue(manager.path_catalogue).get_all()
    assert [(entry.id, entry.name) for entry in loaded] == [("visible", "before")]


def test_completed_write_keeps_the_previous_json_version(tmp_path):
    """Each successful replacement keeps the immediately previous JSON bytes."""
    metadata_path = tmp_path / "snapshot.json"
    SnapshotSerializer.to_json(Snapshot("id", "before", ""), metadata_path)
    previous_bytes = metadata_path.read_bytes()

    SnapshotSerializer.update_field(metadata_path, "name", "after")

    assert SnapshotSerializer.from_json(metadata_path).name == "after"
    assert MetadataFile.previous_path(metadata_path).read_bytes() == previous_bytes
    assert SnapshotSerializer.from_json(MetadataFile.previous_path(metadata_path)).name == "before"


def test_failed_final_rename_preserves_both_current_and_recoverable_versions(tmp_path, monkeypatch):
    """A rename error leaves the old JSON published and the sidecar readable."""
    metadata_path = tmp_path / "snapshot.json"
    SnapshotSerializer.write_text(metadata_path, "old JSON")
    real_replace = MetadataFile._replace_sibling

    def fail_current_replace(source, destination, expected_parent):
        """Allow the sidecar publication but reject the final JSON rename."""
        if destination == metadata_path:
            raise PermissionError("metadata publication denied")
        real_replace(source, destination, expected_parent)

    monkeypatch.setattr(MetadataFile, "_replace_sibling", fail_current_replace)
    with pytest.raises(PermissionError, match="publication denied"):
        SnapshotSerializer.write_text(metadata_path, "new JSON")

    assert metadata_path.read_text(encoding="utf-8") == "old JSON"
    assert MetadataFile.previous_path(metadata_path).read_text(encoding="utf-8") == "old JSON"
    assert not list(tmp_path.glob(".*.tmp"))


def test_post_publication_sync_error_reports_published_but_unconfirmed(tmp_path, monkeypatch):
    """A final directory-flush failure is distinct from a failed publication."""
    metadata_path = tmp_path / "snapshot.json"
    SnapshotSerializer.write_text(metadata_path, "old JSON")
    sync_calls = []

    def sync_parent(path, expected_parent):
        """Allow the backup flush and fail after the current name is replaced."""
        sync_calls.append(path)
        if len(sync_calls) == 1:
            return True
        raise OSError("simulated server flush failure")

    monkeypatch.setattr(MetadataFile, "_sync_parent_directory", sync_parent)
    with pytest.raises(MetadataDurabilityError) as error:
        SnapshotSerializer.write_text(metadata_path, "new JSON")

    assert error.value.published is True
    assert error.value.durability_confirmed is False
    assert metadata_path.read_text(encoding="utf-8") == "new JSON"
    assert MetadataFile.previous_path(metadata_path).read_text(encoding="utf-8") == "old JSON"


def test_full_json_save_uses_atomic_writer_and_preserves_recoverable_bytes(tmp_path):
    """Full and partial serializer writes share the atomic metadata adapter."""
    metadata_path = tmp_path / "snapshot.json"
    SnapshotSerializer.to_json(Snapshot("id", "before", ""), metadata_path)
    previous_bytes = metadata_path.read_bytes()

    SnapshotSerializer.to_json(Snapshot("id", "after", ""), metadata_path)

    assert json.loads(metadata_path.read_text(encoding="utf-8"))["name"] == "after"
    assert MetadataFile.previous_path(metadata_path).read_bytes() == previous_bytes

