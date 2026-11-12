"""Test backup collaborators through their own format and publication contracts."""

import json
import zipfile
from datetime import datetime

import pytest

from pylizlib.core.os.snap.domain import BackupType, Snapshot, SnapshotSettings
from pylizlib.core.os.snap.manager import SnapshotManager
from pylizlib.core.os.snap.operations.backup import creation
from pylizlib.core.os.snap.operations.backup.inspection import BackupArchiveInspector
from pylizlib.core.os.snap.operations.backup_manifest import BACKUP_MANIFEST_NAME, build_backup_manifest
from pylizlib.core.os.snap.operations.backup_names import parse_backup_filename


def test_inspector_uses_embedded_identity_and_preserves_strict_precedence(tmp_path):
    """A modern manifest governs renamed ZIPs, and an invalid one cannot fall back."""
    snapshot = Snapshot("embedded-id", "name", "description")
    manifest = build_backup_manifest(snapshot, BackupType.SNAPSHOT_DIRECTORY, "prefix", False, "20260102_030405")
    archive = tmp_path / "renamed.data"
    inspector = BackupArchiveInspector(SnapshotSettings(), parse_backup_filename)
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr(BACKUP_MANIFEST_NAME, json.dumps(manifest))
    result = inspector.read(archive)
    assert result.info.snapshot_id == "embedded-id"
    assert result.info.prefix == "prefix"
    assert result.info.backup_type == BackupType.SNAPSHOT_DIRECTORY

    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr(BACKUP_MANIFEST_NAME, "{}")
        stream.writestr("snapshot.json", json.dumps({"id": "fallback"}))
    with pytest.raises(ValueError, match="manifest format"):
        inspector.read(archive)


def test_creator_injected_clock_and_concurrent_collision(tmp_path, monkeypatch, caplog):
    """Retrying a concurrent writer retains its bytes and the captured timestamp."""
    manager = SnapshotManager(Snapshot("snapshot", "name", ""), tmp_path / "catalogue")
    manager.create()
    creator = creation.BackupCreator(manager._storage(), now=lambda: datetime(2026, 1, 2, 3, 4, 5))
    write = creation._write_verified_zip_exclusive
    collisions = []

    def concurrent_writer(path, entries, message_callback):
        """Publish the first candidate just before the exclusive hard link."""
        if not collisions:
            path.write_bytes(b"concurrent backup")
            collisions.append(path)
            raise FileExistsError(str(path))
        return write(path, entries, message_callback)

    monkeypatch.setattr(creation, "_write_verified_zip_exclusive", concurrent_writer)
    with caplog.at_level("INFO", logger="PylizLib"):
        result = creator.create_backup(tmp_path / "backups", "prefix", BackupType.SNAPSHOT_DIRECTORY)
    assert "20260102_030405_1.zip" in result.name
    assert collisions[0].read_bytes() == b"concurrent backup"
    assert zipfile.is_zipfile(result)
    assert "Created snapshot backup snapshot=snapshot" in caplog.text
