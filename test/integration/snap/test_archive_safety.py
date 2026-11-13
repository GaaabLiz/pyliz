"""Reject unsafe archive inputs before replacing or publishing snapshot data."""

import json
import zipfile
from pathlib import Path

import pytest

from pylizlib.core.os.snap import BackupType, SequentialFileCopyStrategy, SnapDirAssociation, Snapshot, SnapshotCatalogue, SnapshotIntegrityError, SnapshotManager, SnapshotSerializer, SnapshotSettings


def _captured_snapshot(workspace: Path):
    """Create an isolated, fully manifested snapshot and its SD backup."""
    source = workspace / "source"
    (source / "empty").mkdir(parents=True)
    (source / "payload").write_bytes(b"capture")
    settings = SnapshotSettings()
    catalogue = SnapshotCatalogue(workspace / "catalogue", settings)
    snapshot = Snapshot("captured", "captured snapshot", "", directories=[SnapDirAssociation(0, str(source), "folder")])
    catalogue.add(snapshot)
    manager = SnapshotManager(snapshot, catalogue.path_catalogue, settings)
    archive = manager.create_backup(workspace / "exports", "original", BackupType.SNAPSHOT_DIRECTORY)
    return catalogue, snapshot, manager, archive


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


@pytest.mark.parametrize("target_exists", [False, True])
@pytest.mark.parametrize("damage", ["association", "file", "changed-file", "extra-file", "file-is-directory", "empty-directory"])
def test_sd_restore_validates_content_before_replacing_any_snapshot(snapshot_workspace: Path, target_exists: bool, damage: str) -> None:
    """CRC-valid archives with missing or mismatched contents never replace good data."""
    catalogue, snapshot, manager, original = _captured_snapshot(snapshot_workspace)
    association_name = snapshot.directories[0].directory_name
    broken = snapshot_workspace / "broken.zip"
    with zipfile.ZipFile(original) as source, zipfile.ZipFile(broken, "w") as output:
        for member in source.infolist():
            if damage == "association" and (member.filename.rstrip("/") == association_name or member.filename.startswith(association_name + "/")):
                continue
            if damage in {"file", "file-is-directory"} and member.filename == f"{association_name}/payload":
                continue
            if damage == "empty-directory" and member.filename == f"{association_name}/empty/":
                continue
            content = b"changed" if damage == "changed-file" and member.filename == f"{association_name}/payload" else source.read(member)
            output.writestr(member, content)
        if damage == "extra-file":
            output.writestr(f"{association_name}/extra", b"unexpected")
        if damage == "file-is-directory":
            output.writestr(f"{association_name}/payload/", b"")
    if not target_exists:
        catalogue.delete(snapshot)
    else:
        (manager.path_snapshot / "preserve-previous").write_bytes(b"unique previous data")
    before = {path.relative_to(manager.path_snapshot): path.read_bytes() for path in manager.path_snapshot.rglob("*") if path.is_file()}
    with zipfile.ZipFile(broken) as archive:
        assert archive.testzip() is None

    with pytest.raises(OSError) as error:
        catalogue.restore_backup(broken)
    assert isinstance(error.value.__cause__, FileNotFoundError if damage == "association" else SnapshotIntegrityError)
    assert {path.relative_to(manager.path_snapshot): path.read_bytes() for path in manager.path_snapshot.rglob("*") if path.is_file()} == before
    assert manager.path_snapshot.exists() is target_exists
    assert not list(catalogue.path_catalogue.rglob("journal.json"))


@pytest.mark.parametrize("allow_unverified", [False, True])
def test_sd_restore_retains_explicit_legacy_integrity_policy(snapshot_workspace: Path, allow_unverified: bool) -> None:
    """Restoring legacy data retains unknown integrity; install still applies its own opt-in."""
    catalogue, snapshot, manager, original = _captured_snapshot(snapshot_workspace)
    catalogue.settings.allow_unverified_legacy_snapshots = allow_unverified
    legacy = snapshot_workspace / "legacy.zip"
    with zipfile.ZipFile(original) as source, zipfile.ZipFile(legacy, "w") as output:
        for member in source.infolist():
            content = source.read(member)
            if member.filename == catalogue.settings.json_filename:
                data = json.loads(content)
                for association in data["directories"]:
                    association.pop("integrity_manifest", None)
                content = json.dumps(data).encode()
            output.writestr(member, content)
    catalogue.restore_backup(legacy)
    loaded = catalogue.get_by_id(snapshot.id)
    assert loaded is not None
    assert loaded.directories[0].integrity_manifest is None
    assert (manager.path_snapshot / loaded.directories[0].directory_name / "payload").read_bytes() == b"capture"


def test_sd_restore_verifies_the_copied_tree_instead_of_only_the_archive(snapshot_workspace: Path) -> None:
    """A copy fault after valid extraction cannot replace the existing good snapshot."""
    catalogue, snapshot, manager, archive = _captured_snapshot(snapshot_workspace)
    association_name = snapshot.directories[0].directory_name
    before_json = manager.path_snapshot_json.read_bytes()

    class CorruptingStrategy(SequentialFileCopyStrategy):
        """Simulate a copy backend returning changed bytes despite success."""

        def copy_directory(self, source, destination, *args, **kwargs):
            """Change a completed staging file, retaining a valid copied JSON manifest."""
            copied = super().copy_directory(source, destination, *args, **kwargs)
            (copied / association_name / "payload").write_bytes(b"changed")
            return copied

    catalogue.settings.copy_strategy = CorruptingStrategy()
    with pytest.raises(OSError) as error:
        catalogue.restore_backup(archive)
    assert isinstance(error.value.__cause__, SnapshotIntegrityError)
    assert manager.path_snapshot_json.read_bytes() == before_json
    assert (manager.path_snapshot / association_name / "payload").read_bytes() == b"capture"
