"""Exercise field-based creation and partial edits through the public catalogue."""

from pathlib import Path

import pytest

from pylizlib.core.os.snap import SnapshotCatalogue, SnapshotSettings


def test_create_and_edit_from_fields(snapshot_workspace: Path) -> None:
    first, second, added = (snapshot_workspace / label for label in ("first", "second", "added"))
    for source in (first, second, added):
        source.mkdir()
        (source / "data.txt").write_text(source.name, encoding="utf-8")
    (second / "child").mkdir()
    catalogue = SnapshotCatalogue(
        snapshot_workspace / "catalogue",
        SnapshotSettings(folder_id_length=10, backup_path=snapshot_workspace / "backups", backup_pre_modify=True),
    )
    progress = []
    snapshot = catalogue.create_snapshot(
        snap_id="configuration",
        name="Original name",
        desc="Original description",
        author="Original author",
        directory_paths=[str(first), second],
        tags=["original"],
        data={"hidden": "keep", "visible": "old", "obsolete": "remove"},
        progress_callback=progress.append,
    )
    assert progress[-1] == 100
    assert all(len(association.folder_id) == 10 for association in snapshot.directories)
    assert catalogue.get_by_id(snapshot.id) == snapshot
    assert snapshot.capture_completed_at is not None

    original_second = snapshot.directories[1]
    (second / "data.txt").write_text("local change", encoding="utf-8")
    catalogue.settings.folder_id_length = 8
    updated = catalogue.update_snapshot(
        snapshot.id,
        name="New name",
        directory_paths=[second / "child" / "..", added],
        data_updates={"visible": "new"},
        data_remove=["obsolete"],
    )
    retained, new = updated.directories
    assert updated.name == "New name"
    assert updated.desc == snapshot.desc
    assert updated.author == snapshot.author
    assert updated.date_created == snapshot.date_created
    assert updated.capture_completed_at == snapshot.capture_completed_at
    assert updated.tags == ["original"]
    assert updated.data == {"hidden": "keep", "visible": "new"}
    assert retained.folder_id == original_second.folder_id
    assert retained.original_path == original_second.original_path
    assert retained.directory_name == original_second.directory_name
    assert retained.integrity_manifest == original_second.integrity_manifest
    assert retained.mb_size == original_second.mb_size
    assert (retained.index, new.index) == (0, 1)
    assert len(new.folder_id) == 8
    assert new.integrity_manifest is not None
    root = catalogue.path_catalogue / snapshot.id
    assert (root / retained.directory_name / "data.txt").read_text(encoding="utf-8") == "second"
    assert not (root / snapshot.directories[0].directory_name).exists()
    assert (root / new.directory_name / "data.txt").read_text(encoding="utf-8") == "added"
    assert catalogue.get_by_id(snapshot.id) == updated
    assert catalogue.get_backup_count() == 1
    (before_edit,) = catalogue.list_backups(catalogue.settings.backup_path)
    restored_catalogue = SnapshotCatalogue(snapshot_workspace / "restored")
    restored_catalogue.restore_backup(before_edit.path)
    assert restored_catalogue.get_by_id(snapshot.id) == snapshot

    metadata_edit = catalogue.update_snapshot(snapshot.id, desc="", tags=[], data_updates={"hidden": ""})
    assert metadata_edit.directories == updated.directories
    assert metadata_edit.desc == ""
    assert metadata_edit.tags == []
    assert metadata_edit.data == {"hidden": "", "visible": "new"}
    assert catalogue.update_snapshot(snapshot.id, directory_paths=[]).directories == []


def test_invalid_path_edits_leave_the_snapshot_unchanged(snapshot_workspace: Path) -> None:
    source = snapshot_workspace / "source"
    (source / "subdir").mkdir(parents=True)
    catalogue = SnapshotCatalogue(snapshot_workspace / "catalogue")

    with pytest.raises(ValueError, match="Duplicate snapshot directory"):
        catalogue.create_snapshot(snap_id="duplicate-path", name="Duplicate", directory_paths=[source, source / "subdir" / ".."])
    assert catalogue.get_by_id("duplicate-path") is None

    snapshot = catalogue.create_snapshot(snap_id="configuration", name="Original", directory_paths=[source])
    with pytest.raises(ValueError, match="Duplicate snapshot directory"):
        catalogue.update_snapshot(snapshot.id, name="Duplicate", directory_paths=[source, source / "subdir" / ".."])
    with pytest.raises(FileNotFoundError):
        catalogue.update_snapshot(snapshot.id, name="Missing source", directory_paths=[snapshot_workspace / "missing"])
    with pytest.raises(ValueError, match="No snapshot found"):
        catalogue.update_snapshot("unknown", name="Unknown")

    assert catalogue.get_by_id(snapshot.id) == snapshot
    assert (catalogue.path_catalogue / snapshot.id / snapshot.directories[0].directory_name).is_dir()
