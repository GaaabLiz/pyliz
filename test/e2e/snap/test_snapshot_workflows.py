"""Public snapshot workflows against isolated, real filesystem trees."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from pylizlib.core.os.snap import (
    BackupType,
    SnapDirAssociation,
    Snapshot,
    SnapshotCatalogue,
    SnapshotIncompleteError,
    SnapshotIntegrityError,
    SnapshotManager,
    SnapshotSearcher,
    SnapshotSearchParams,
    SnapshotSettings,
)
from pylizlib.core.os.snap.searcher import SearchTarget


def make_source(root: Path, name: str, *, text: str = "captured version") -> Path:
    """Create a source tree containing binary data and empty directories."""
    source = root / "sources" / name
    (source / "nested" / "empty").mkdir(parents=True)
    (source / "empty-root").mkdir()
    (source / "readme.txt").write_text(text, encoding="utf-8")
    (source / "nested" / "payload.bin").write_bytes(b"\x00\x01snapshot\xff\x10")
    return source


def make_snapshot(snapshot_id: str, source: Path, folder_id: str = "folder-main") -> Snapshot:
    return Snapshot(
        id=snapshot_id,
        name=f"E2E {snapshot_id}",
        desc="Snapshot E2E scenario",
        author="pylizlib E2E",
        directories=[SnapDirAssociation(index=1, original_path=str(source), folder_id=folder_id)],
        tags=["e2e"],
    )


def association_copy(catalogue: SnapshotCatalogue, snapshot: Snapshot, association: SnapDirAssociation) -> Path:
    snapshot_root = catalogue.get_snap_directory_path(snapshot)
    assert snapshot_root is not None
    return snapshot_root / association.directory_name


def test_create_search_sync_and_install(snapshot_workspace: Path) -> None:
    source = make_source(snapshot_workspace, "lifecycle")
    catalogue = SnapshotCatalogue(snapshot_workspace / "catalogue")
    snapshot = make_snapshot("e2e_lifecycle", source)
    creation_progress: list[int] = []
    messages: list[str] = []

    catalogue.add(snapshot, progress_callback=creation_progress.append, message_callback=messages.append)

    loaded = catalogue.get_by_id(snapshot.id)
    assert loaded is not None
    assert catalogue.exists(snapshot.id)
    assert len(catalogue.get_all()) == 1
    assert creation_progress[-1] == 100
    assert loaded.capture_started_at is not None and loaded.capture_started_at.utcoffset() is not None
    assert loaded.capture_completed_at is not None and loaded.capture_completed_at.utcoffset() is not None

    stored = association_copy(catalogue, loaded, loaded.directories[0])
    assert (stored / "readme.txt").read_text(encoding="utf-8") == "captured version"
    assert (stored / "nested" / "payload.bin").read_bytes() == b"\x00\x01snapshot\xff\x10"
    assert (stored / "empty-root").is_dir()
    assert (stored / "nested" / "empty").is_dir()

    manifest = loaded.directories[0].integrity_manifest
    assert manifest is not None
    assert manifest["readme.txt"] == {
        "type": "file",
        "size": len(b"captured version"),
        "sha256": hashlib.sha256(b"captured version").hexdigest(),
    }
    assert manifest["empty-root"] == {"type": "directory", "size": 0, "sha256": None}

    results = SnapshotSearcher(catalogue).search(
        loaded,
        SnapshotSearchParams(query="captured version", search_target=SearchTarget.FILE_CONTENT),
    )
    assert len(results) == 1
    assert results[0].file_path.name == "readme.txt"

    # Synchronize edits made to the original directory into the stored copy.
    (source / "readme.txt").write_text("synchronized version", encoding="utf-8")
    (source / "added.txt").write_text("new file", encoding="utf-8")
    catalogue.update_assoc_with_installed(snapshot.id, message_callback=messages.append)
    loaded = catalogue.get_by_id(snapshot.id)
    assert loaded is not None
    stored = association_copy(catalogue, loaded, loaded.directories[0])
    assert (stored / "readme.txt").read_text(encoding="utf-8") == "synchronized version"
    assert (stored / "added.txt").read_text(encoding="utf-8") == "new file"
    assert loaded.directories[0].integrity_manifest is not None
    assert "added.txt" in loaded.directories[0].integrity_manifest

    # Merge mode retains unrelated live files; replace mode removes them.
    (source / "untracked.txt").write_text("preserve during merge", encoding="utf-8")
    catalogue.install(loaded, clear_destination=False, message_callback=messages.append)
    assert (source / "untracked.txt").exists()

    (source / "readme.txt").write_text("unwanted live data", encoding="utf-8")
    (source / "remove-on-replace.txt").write_text("temporary", encoding="utf-8")
    install_progress: list[int] = []
    catalogue.install(loaded, clear_destination=True, progress_callback=install_progress.append)
    assert (source / "readme.txt").read_text(encoding="utf-8") == "synchronized version"
    assert (source / "added.txt").read_text(encoding="utf-8") == "new file"
    assert not (source / "untracked.txt").exists()
    assert not (source / "remove-on-replace.txt").exists()
    assert install_progress[-1] == 100

    # Removing installed copies affects the live target but leaves the snapshot.
    catalogue.remove_installed_copies(snapshot.id)
    assert not source.exists()
    assert catalogue.exists(snapshot.id)
    catalogue.install(loaded)
    assert (source / "readme.txt").read_text(encoding="utf-8") == "synchronized version"

    catalogue.delete(loaded, message_callback=messages.append)
    assert not catalogue.exists(snapshot.id)
    assert messages


def test_association_edits_and_duplicate_are_independent(snapshot_workspace: Path) -> None:
    source_a = make_source(snapshot_workspace, "association-a", text="first association")
    source_b = make_source(snapshot_workspace, "association-b", text="second association")
    catalogue = SnapshotCatalogue(snapshot_workspace / "catalogue")
    snapshot = make_snapshot("e2e_edits", source_a, "assoc-a")
    catalogue.add(snapshot)

    old = catalogue.get_by_id(snapshot.id)
    assert old is not None
    updated = old.clone()
    updated.name = "Metadata changed through the catalogue API"
    updated.directories.append(SnapDirAssociation(index=2, original_path=str(source_b), folder_id="assoc-b"))
    catalogue.update_snapshot_by_objs(old, updated)

    loaded = catalogue.get_by_id(snapshot.id)
    assert loaded is not None
    assert loaded.name == updated.name
    assert {item.folder_id for item in loaded.directories} == {"assoc-a", "assoc-b"}
    second_copy = association_copy(catalogue, loaded, next(item for item in loaded.directories if item.folder_id == "assoc-b"))
    assert (second_copy / "readme.txt").read_text(encoding="utf-8") == "second association"

    # Removing one stable folder_id must not remove the remaining association.
    remove_first = loaded.clone()
    remove_first.directories = [item for item in remove_first.directories if item.folder_id == "assoc-b"]
    catalogue.update_snapshot_by_objs(loaded, remove_first)
    loaded = catalogue.get_by_id(snapshot.id)
    assert loaded is not None
    assert [item.folder_id for item in loaded.directories] == ["assoc-b"]
    assert second_copy.is_dir()
    assert (second_copy / "readme.txt").read_text(encoding="utf-8") == "second association"

    catalogue.duplicate_by_id(snapshot.id)
    snapshots = catalogue.get_all()
    assert len(snapshots) == 2
    duplicate = next(item for item in snapshots if item.id != snapshot.id)
    duplicate_assoc = duplicate.directories[0]
    duplicate_file = association_copy(catalogue, duplicate, duplicate_assoc) / "readme.txt"
    duplicate_file.write_text("changed only in duplicate", encoding="utf-8")

    original = catalogue.get_by_id(snapshot.id)
    assert original is not None
    original_assoc = original.directories[0]
    original_file = association_copy(catalogue, original, original_assoc) / "readme.txt"
    assert original_file.read_text(encoding="utf-8") == "second association"

    catalogue.delete(duplicate)
    catalogue.delete(original)
    assert catalogue.get_all() == []


def test_archive_export_import_and_standalone_restore(snapshot_workspace: Path) -> None:
    source = make_source(snapshot_workspace, "archive-source", text="archive payload")
    catalogue_path = snapshot_workspace / "catalogue"
    settings = SnapshotSettings(backup_path=snapshot_workspace / "automatic-backups")
    catalogue = SnapshotCatalogue(catalogue_path, settings)
    snapshot = make_snapshot("e2e_archives", source)
    catalogue.add(snapshot)
    loaded = catalogue.get_by_id(snapshot.id)
    assert loaded is not None
    manager = SnapshotManager(loaded, catalogue_path, settings)

    export_dir = snapshot_workspace / "exports"
    export_dir.mkdir()
    snapshot_export = manager.create_backup(export_dir, "snapshot-export", BackupType.SNAPSHOT_DIRECTORY, is_export=True)
    snapshot_export_again = manager.create_backup(export_dir, "snapshot-export", BackupType.SNAPSHOT_DIRECTORY, is_export=True)
    assert snapshot_export != snapshot_export_again
    assert snapshot_export.is_file() and snapshot_export_again.is_file()

    associated_archive = manager.create_backup(export_dir, "associated-export", BackupType.ASSOCIATED_DIRECTORIES, is_export=True)
    renamed_associated_archive = associated_archive.with_name("renamed-package.zip")
    associated_archive.rename(renamed_associated_archive)
    listed = catalogue.list_backups(export_dir)
    assert any(item.path == renamed_associated_archive and item.backup_type is BackupType.ASSOCIATED_DIRECTORIES for item in listed)

    mapped_target = snapshot_workspace / "remapped-target"
    mapped_catalogue = SnapshotCatalogue(snapshot_workspace / "standalone-catalogue")
    mapped_catalogue.restore_backup_with_mapping(
        renamed_associated_archive,
        {loaded.directories[0].folder_id: mapped_target},
    )
    assert (mapped_target / "readme.txt").read_text(encoding="utf-8") == "archive payload"
    assert (mapped_target / "nested" / "payload.bin").read_bytes() == b"\x00\x01snapshot\xff\x10"
    assert (mapped_target / "nested" / "empty").is_dir()

    snapshot_export_dir = snapshot_workspace / "snapshot-export-dir"
    snapshot_export_dir.mkdir()
    catalogue.export_snapshot(snapshot.id, snapshot_export_dir)
    single_snapshot_archive = next(snapshot_export_dir.glob("*.zip"))
    imported_catalogue = SnapshotCatalogue(snapshot_workspace / "imported-single")
    imported_catalogue.import_snapshot(single_snapshot_archive)
    imported = imported_catalogue.get_by_id(snapshot.id)
    assert imported is not None
    imported_copy = association_copy(imported_catalogue, imported, imported.directories[0])
    assert (imported_copy / "readme.txt").read_text(encoding="utf-8") == "archive payload"
    assert (imported_copy / "empty-root").is_dir()

    catalogue_export_dir = snapshot_workspace / "catalogue-export"
    catalogue_export = catalogue.export_catalogue(catalogue_export_dir, "catalogue.zip")
    assert catalogue_export is not None and catalogue_export.is_file()
    imported_full_catalogue = SnapshotCatalogue(snapshot_workspace / "imported-catalogue")
    imported_full_catalogue.import_catalogue(catalogue_export)
    assert [item.id for item in imported_full_catalogue.get_all()] == [snapshot.id]

    # A snapshot-directory backup can recover a deleted catalogue entry.
    catalogue.delete(loaded)
    assert not catalogue.exists(snapshot.id)
    catalogue.restore_backup(snapshot_export)
    assert catalogue.exists(snapshot.id)
    restored = catalogue.get_by_id(snapshot.id)
    assert restored is not None
    restored_copy = association_copy(catalogue, restored, restored.directories[0])
    assert (restored_copy / "readme.txt").read_text(encoding="utf-8") == "archive payload"

    catalogue.delete_backup(snapshot_export_again)
    assert not snapshot_export_again.exists()


def test_corruption_and_missing_source_are_reported_before_destructive_work(snapshot_workspace: Path) -> None:
    source = make_source(snapshot_workspace, "integrity", text="known good data")
    catalogue_path = snapshot_workspace / "catalogue"
    catalogue = SnapshotCatalogue(catalogue_path)
    snapshot = make_snapshot("e2e_integrity", source)
    catalogue.add(snapshot)
    loaded = catalogue.get_by_id(snapshot.id)
    assert loaded is not None
    association = loaded.directories[0]
    stored = association_copy(catalogue, loaded, association)

    (source / "readme.txt").write_text("live target remains", encoding="utf-8")
    (stored / "readme.txt").write_text("corrupted stored bytes", encoding="utf-8")
    with pytest.raises(SnapshotIntegrityError):
        catalogue.install(loaded)
    assert (source / "readme.txt").read_text(encoding="utf-8") == "live target remains"

    source.rename(source.with_name("source-moved-away"))
    with pytest.raises(SnapshotIncompleteError) as error:
        catalogue.export_assoc_dirs(snapshot.id, snapshot_workspace / "incomplete-backups")
    assert error.value.missing_folders == [association.original_path]

    catalogue.delete(loaded)
