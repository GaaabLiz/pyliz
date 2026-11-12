"""Test backup collaborators through their own format and publication contracts."""

import json
import platform
import zipfile
from datetime import datetime

import pytest

from pylizlib.core.os.snap.copy_strategy import SequentialFileCopyStrategy
from pylizlib.core.os.snap.domain import BackupType, Snapshot, SnapshotSettings
from pylizlib.core.os.snap.manager import SnapshotManager
from pylizlib.core.os.snap.operations.backup import creation
from pylizlib.core.os.snap.operations.backup.inspection import BackupArchiveInspector
from pylizlib.core.os.snap.operations.backup.planning import RestorePlanner
from pylizlib.core.os.snap.operations.backup.restore import AssociationRestorer
from pylizlib.core.os.snap.operations.backup_manifest import BACKUP_MANIFEST_NAME, ArchivedAssociation, build_backup_manifest
from pylizlib.core.os.snap.operations.backup_names import parse_backup_filename
from pylizlib.core.os.snap.operations.transfers import CatalogueTransferService
from pylizlib.core.os.snap.serializer import SnapshotSerializer


def test_inspector_uses_embedded_identity_and_preserves_strict_precedence(tmp_path, caplog):
    """A modern manifest governs renamed ZIPs, and an invalid one cannot fall back."""
    snapshot = Snapshot("embedded-id", "name", "description")
    manifest = build_backup_manifest(snapshot, BackupType.SNAPSHOT_DIRECTORY, "prefix", False, "20260102_030405")
    archive = tmp_path / "renamed.data"
    inspector = BackupArchiveInspector(SnapshotSettings(), parse_backup_filename)
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr(BACKUP_MANIFEST_NAME, json.dumps(manifest))
    with caplog.at_level("DEBUG", logger="PylizLib"):
        result = inspector.read(archive)
    assert result.info.snapshot_id == "embedded-id"
    assert result.info.prefix == "prefix"
    assert result.info.backup_type == BackupType.SNAPSHOT_DIRECTORY
    assert "format=modern" in caplog.text
    assert "description" not in caplog.text

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


def test_restore_stages_every_copy_before_modifying_targets(tmp_path, monkeypatch):
    """Failure on the second staging copy leaves both original targets untouched."""

    class FailSecondCopy(SequentialFileCopyStrategy):
        """Copy once, then simulate an unavailable second extracted source."""

        calls = 0

        def copy_directory(self, source, destination, *args, **kwargs):
            """Fail the second call before any directory is published."""
            self.calls += 1
            if self.calls == 2:
                raise OSError("second copy failed")
            return super().copy_directory(source, destination, *args, **kwargs)

    catalogue = tmp_path / "catalogue"
    catalogue.mkdir()
    extracted = tmp_path / "extracted"
    extracted.mkdir()
    associations = []
    for name in ("one", "two"):
        target = tmp_path / name
        target.mkdir()
        (target / "content").write_text("old")
        source = extracted / name
        source.mkdir()
        (source / "content").write_text("new")
        associations.append(ArchivedAssociation(name, 1, name, str(target)))
    settings = SnapshotSettings(copy_strategy=FailSecondCopy())
    # This unit isolates staging; destination-policy tests cover critical paths.
    monkeypatch.setattr("pylizlib.core.os.snap.operations.destinations.is_critical_system_path", lambda path: False)
    planner = RestorePlanner(catalogue, settings, lookup=None)
    tasks = planner.build(extracted, associations, None, None, platform.system())
    assert all(task.extracted_dir.parent == extracted for task in tasks)
    assert all(task.staged_dir.parent == task.destination.parent for task in tasks)

    with pytest.raises(OSError, match="second copy failed"):
        AssociationRestorer(planner).execute(tasks)

    assert [(task.destination / "content").read_text() for task in tasks] == ["old", "old"]
    assert all(not task.staged_dir.exists() and not task.backup_dest.exists() for task in tasks)
    assert not (catalogue / ".pyliz_transactions").exists()


@pytest.mark.parametrize(
    ("member", "message"),
    [(BACKUP_MANIFEST_NAME, "Snapshot backup manifest"), (".pyliz_ad_manifest.json", "Associated-directories manifest"), ("snapshot.json", "Snapshot-directory metadata")],
)
def test_each_metadata_format_retains_its_decode_error(tmp_path, member, message):
    """Common JSON decoding preserves format-specific diagnostics and the cause."""
    archive = tmp_path / "backup.zip"
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr(member, b"\xff")
    inspector = BackupArchiveInspector(SnapshotSettings(), parse_backup_filename)
    with pytest.raises(ValueError, match=message + " is invalid") as error:
        inspector.read(archive)
    assert isinstance(error.value.__cause__, UnicodeDecodeError)


def test_import_metadata_phase_keeps_valid_manifest_cleanup_and_type_errors(tmp_path):
    """A matching SD manifest is removed; an AD manifest is retained and rejected."""
    snapshot = Snapshot("id", "name", "")
    SnapshotSerializer.to_json(snapshot, tmp_path / "snapshot.json")
    manifest = build_backup_manifest(snapshot, BackupType.ASSOCIATED_DIRECTORIES, "", False, "20260101_000000")
    manifest_path = tmp_path / BACKUP_MANIFEST_NAME
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    service = CatalogueTransferService(tmp_path, SnapshotSettings(), query=None)
    with pytest.raises(ValueError, match="does not match its snapshot JSON"):
        service._read_imported_snapshot(tmp_path)
    assert manifest_path.is_file()
    manifest["backup_type"] = "snapshot_directory"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    assert service._read_imported_snapshot(tmp_path).id == "id"
    assert not manifest_path.exists()
