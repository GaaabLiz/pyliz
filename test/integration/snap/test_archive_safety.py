"""Reject unsafe archive inputs before replacing or publishing snapshot data."""

import json
import zipfile
from pathlib import Path

import pytest

from pylizlib.core.os.snap import BackupType, SnapDirAssociation, Snapshot, SnapshotCatalogue, SnapshotManager, SnapshotSerializer, SnapshotSettings


@pytest.mark.parametrize("entry_point", ["import_snapshot", "import_catalogue", "restore_backup"])
@pytest.mark.parametrize("transaction_name", [".pyliz_transactions", ".PYLIZ_TRANSACTIONS", ".pyliz_transactions. "])
def test_archive_journals_are_rejected_before_publication(snapshot_workspace: Path, entry_point: str, transaction_name: str) -> None:
    """Incoming recovery instructions never reach the locally trusted store."""
    catalogue = SnapshotCatalogue(snapshot_workspace / "catalogue", SnapshotSettings())
    existing = Snapshot("existing", "original metadata", "")
    catalogue.add(existing)
    metadata_path = catalogue.path_catalogue / existing.id / catalogue.settings.json_filename
    original_metadata = metadata_path.read_bytes()
    victim = snapshot_workspace / "unrelated"
    victim.mkdir()
    sentinel = victim / "important"
    sentinel.write_bytes(b"must survive importing and looking up an archive")
    snapshot_id = existing.id if entry_point == "restore_backup" else "incoming"
    incoming = Snapshot(snapshot_id, "archive metadata", "")
    metadata_source = snapshot_workspace / "metadata.json"
    SnapshotSerializer.to_json(incoming, metadata_source)
    journal = {
        "version": 1,
        "scope_root": (catalogue.path_catalogue / snapshot_id).as_posix(),
        "operation": "restore_associations_manifest",
        "state": "prepared",
        "payload": {
            "entries": [
                {
                    "folder_id": "unrelated-to-the-imported-snapshot",
                    "stage": str(snapshot_workspace / "unrelated_staging_test"),
                    "destination": str(victim),
                    "backup": str(snapshot_workspace / "unrelated_bck_test"),
                    "had_original": False,
                }
            ]
        },
    }
    prefix = f"{snapshot_id}/" if entry_point == "import_catalogue" else ""
    archive = snapshot_workspace / "incoming.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.write(metadata_source, prefix + catalogue.settings.json_filename)
        output.writestr(f"{prefix}{transaction_name}/injected/journal.json", json.dumps(journal))

    with pytest.raises(ValueError, match="[Tt]ransaction"):
        getattr(catalogue, entry_point)(archive)

    assert [(snapshot.id, snapshot.name) for snapshot in catalogue.get_all()] == [(existing.id, existing.name)]
    assert metadata_path.read_bytes() == original_metadata
    assert sentinel.read_bytes() == b"must survive importing and looking up an archive"
    assert not list(catalogue.path_catalogue.rglob("journal.json"))


def test_catalogue_import_preflights_all_entries_before_publishing(snapshot_workspace: Path) -> None:
    """An unsafe second entry must leave even the first valid entry unpublished."""
    catalogue = SnapshotCatalogue(snapshot_workspace / "catalogue", SnapshotSettings())
    archive = snapshot_workspace / "catalogue.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("first/snapshot.json", '{"id": "first"}')
        output.writestr("second/snapshot.json", '{"id": "second"}')
        output.writestr("second/.pyliz_transactions/injected/journal.json", "{}")
    with pytest.raises(ValueError, match="transaction"):
        catalogue.import_catalogue(archive)
    assert not (catalogue.path_catalogue / "first").exists()
    assert not (catalogue.path_catalogue / "second").exists()


@pytest.mark.parametrize("entry_point", ["import_snapshot", "import_catalogue", "restore_backup"])
def test_nested_user_journal_names_remain_ordinary_snapshot_content(snapshot_workspace: Path, entry_point: str) -> None:
    """The reserved-root policy does not discard user files inside associations."""
    source = snapshot_workspace / "source"
    user_data = source / ".pyliz_transactions" / "journal.json"
    user_data.parent.mkdir(parents=True)
    user_data.write_bytes(b"ordinary data, never a recovery instruction")
    settings = SnapshotSettings()
    snapshot = Snapshot("nested-data", "nested user data", "", directories=[SnapDirAssociation(0, str(source), "folder")])
    original = SnapshotCatalogue(snapshot_workspace / "original", settings)
    original.add(snapshot)
    exports = snapshot_workspace / "exports"
    if entry_point == "import_catalogue":
        archive = original.export_catalogue(exports)
    else:
        archive = SnapshotManager(snapshot, original.path_catalogue, settings).create_backup(exports, "data", BackupType.SNAPSHOT_DIRECTORY)
    assert archive is not None
    imported = SnapshotCatalogue(snapshot_workspace / "imported", SnapshotSettings())
    getattr(imported, entry_point)(archive)
    loaded = imported.get_by_id(snapshot.id)
    assert loaded is not None
    captured = imported.path_catalogue / loaded.id / loaded.directories[0].directory_name / ".pyliz_transactions" / "journal.json"
    assert captured.read_bytes() == user_data.read_bytes()
