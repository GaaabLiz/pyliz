"""Verify that catalogue results report the archive actually produced."""

from pathlib import Path
from zipfile import ZipFile

import pytest

from pylizlib.core.os.snap import BackupType, SnapshotCatalogue, SnapshotSettings, SourceChangedError
from pylizlib.core.os.snap.operations.archives import SnapshotArchiveService


def test_install_reports_skipped_and_partial_backups(snapshot_workspace: Path) -> None:
    saved, missing = (snapshot_workspace / label for label in ("saved", "missing"))
    for folder in (saved, missing):
        folder.mkdir()
        (folder / "captured.txt").write_text("captured contents", encoding="utf-8")
    backups = snapshot_workspace / "backups"
    catalogue = SnapshotCatalogue(
        snapshot_workspace / "catalogue",
        SnapshotSettings(backup_path=backups, backup_pre_install=True),
    )
    snap = catalogue.create_snapshot(snap_id="sample", name="Sample", directory_paths=[saved, missing])
    for folder in (saved, missing):
        (folder / "captured.txt").unlink()
        folder.rmdir()

    result = catalogue.install_with_result(snap)
    assert result.backup_path is None
    assert catalogue.get_backup_count() == 0
    assert (saved / "captured.txt").is_file()
    assert (missing / "captured.txt").is_file()

    (saved / "captured.txt").write_text("local contents", encoding="utf-8")
    (missing / "captured.txt").unlink()
    missing.rmdir()
    result = catalogue.install_with_result(snap)
    archive = result.backup_path
    assert archive is not None and archive.parent == backups
    assert catalogue.list_backups(backups)[0].path == archive
    with ZipFile(archive) as backup:
        files = [name for name in backup.namelist() if name.endswith("/captured.txt")]
        assert len(files) == 1
        assert backup.read(files[0]) == b"local contents"
    assert (missing / "captured.txt").is_file()
    assert (saved / "captured.txt").read_text(encoding="utf-8") == "captured contents"


def test_failed_automatic_backup_stops_install(snapshot_workspace: Path) -> None:
    source = snapshot_workspace / "source"
    source.mkdir()
    local_file = source / "data.txt"
    local_file.write_text("captured", encoding="utf-8")
    blocked_backup_directory = snapshot_workspace / "backups"
    blocked_backup_directory.touch()
    catalogue = SnapshotCatalogue(
        snapshot_workspace / "catalogue",
        SnapshotSettings(backup_path=blocked_backup_directory, backup_pre_install=True),
    )
    snap = catalogue.create_snapshot(snap_id="sample", name="Sample", directory_paths=[source])
    local_file.write_text("local", encoding="utf-8")

    with pytest.raises(FileExistsError):
        catalogue.install_with_result(snap)
    assert local_file.read_text(encoding="utf-8") == "local"
    assert snap.date_last_used is None


@pytest.mark.parametrize("clear_destination", [True, False])
def test_install_backs_up_changes_made_during_staging(snapshot_workspace: Path, clear_destination: bool) -> None:
    source = snapshot_workspace / "source"
    source.mkdir()
    file = source / "data.txt"
    file.write_text("captured", encoding="utf-8")
    catalogue = SnapshotCatalogue(
        snapshot_workspace / "catalogue",
        SnapshotSettings(
            backup_path=snapshot_workspace / "backups",
            backup_pre_install=True,
        ),
    )
    snapshot = catalogue.create_snapshot(snap_id="sample", name="Sample", directory_paths=[source])
    file.write_text("before staging", encoding="utf-8")

    def during_staging(_progress: int) -> None:
        file.write_text("written during staging", encoding="utf-8")

    result = catalogue.install_with_result(snapshot, clear_destination=clear_destination, progress_callback=during_staging)
    assert file.read_text(encoding="utf-8") == "captured"
    assert result.backup_path is not None
    catalogue.restore_backup(result.backup_path)
    assert file.read_text(encoding="utf-8") == "written during staging"


@pytest.mark.parametrize("clear_destination", [True, False])
def test_install_rolls_back_if_a_displaced_file_changed_after_backup(snapshot_workspace: Path, monkeypatch: pytest.MonkeyPatch, clear_destination: bool) -> None:
    source = snapshot_workspace / "source"
    source.mkdir()
    file = source / "data.txt"
    file.write_text("captured", encoding="utf-8")
    catalogue = SnapshotCatalogue(
        snapshot_workspace / "catalogue",
        SnapshotSettings(
            backup_path=snapshot_workspace / "backups",
            backup_pre_install=True,
        ),
    )
    snapshot = catalogue.create_snapshot(snap_id="sample", name="Sample", directory_paths=[source])
    file.write_text("before", encoding="utf-8")
    create_backup = SnapshotArchiveService.create_backup_for_existing_associations

    def write_late(self, *args, **kwargs):
        result = create_backup(self, *args, **kwargs)
        file.write_text("edited", encoding="utf-8")
        return result

    monkeypatch.setattr(SnapshotArchiveService, "create_backup_for_existing_associations", write_late)
    with pytest.raises(SourceChangedError, match="changed after backup"):
        catalogue.install_with_result(snapshot, clear_destination=clear_destination)
    assert file.read_text(encoding="utf-8") == "edited"
    assert catalogue.get_by_id(snapshot.id).date_last_used is None


@pytest.mark.parametrize("enabled", [False, True])
def test_edit_sync_and_delete_report_only_their_own_backups(snapshot_workspace: Path, enabled: bool) -> None:
    source = snapshot_workspace / "source"
    source.mkdir()
    backups = snapshot_workspace / "backups"
    catalogue = SnapshotCatalogue(
        snapshot_workspace / "catalogue",
        SnapshotSettings(backup_path=backups, backup_pre_modify=enabled, backup_pre_delete=enabled),
    )
    snap = catalogue.create_snapshot(snap_id="sample", name="Sample", directory_paths=[source])

    edited = catalogue.update_snapshot_with_result(snap.id, name="Edited")
    assert edited.snapshot == catalogue.get_by_id(snap.id)
    assert edited.snapshot.name == "Edited"
    synced = catalogue.sync_with_result(snap.id)
    deleted = catalogue.delete_with_result(edited.snapshot)

    reported = [result.backup_path for result in (edited, synced, deleted)]
    if enabled:
        listed = catalogue.list_backups(backups)
        assert len(set(reported)) == len(listed) == 3
        assert {entry.path for entry in listed} == set(reported)
        assert all(entry.backup_type is BackupType.SNAPSHOT_DIRECTORY for entry in listed)
    else:
        assert reported == [None, None, None]
        assert catalogue.get_backup_count() == 0
    assert catalogue.get_by_id(snap.id) is None


def test_removal_reports_its_backup_and_skips_when_nothing_is_installed(snapshot_workspace: Path) -> None:
    source = snapshot_workspace / "source"
    source.mkdir()
    backups = snapshot_workspace / "backups"
    catalogue = SnapshotCatalogue(snapshot_workspace / "catalogue", SnapshotSettings(backup_path=backups))
    snap = catalogue.create_snapshot(snap_id="sample", name="Sample", directory_paths=[source])
    assert catalogue.remove_installed_copies_with_result(snap.id).backup_path is None
    assert source.is_dir()

    catalogue.install(snap)
    (source / "local.txt").write_text("local", encoding="utf-8")
    result = catalogue.remove_installed_copies_with_result(snap.id)
    assert result.backup_path is not None
    assert catalogue.list_backups(backups)[0].path == result.backup_path
    assert not source.exists()
    assert catalogue.remove_installed_copies_with_result(snap.id).backup_path is None
    assert catalogue.get_backup_count() == 1


@pytest.mark.parametrize("change_after_backup", [False, True])
def test_merge_backup_uses_real_local_spelling(snapshot_workspace: Path, monkeypatch: pytest.MonkeyPatch, change_after_backup: bool) -> None:
    source = snapshot_workspace / "source"
    source.mkdir()
    captured = source / "Settings.txt"
    captured.write_text("captured", encoding="utf-8")
    local = source / "settings.txt"
    if not local.exists():
        pytest.skip("Requires a case-insensitive volume")

    catalogue = SnapshotCatalogue(
        snapshot_workspace / "catalogue",
        SnapshotSettings(backup_path=snapshot_workspace / "backups", backup_pre_install=True),
    )
    snapshot = catalogue.create_snapshot(snap_id="sample", name="Sample", directory_paths=[source])
    captured.unlink()
    local.write_text("before merge", encoding="utf-8")
    assert [file.name for file in source.iterdir()] == ["settings.txt"]

    if change_after_backup:
        create_backup = SnapshotArchiveService.create_backup_for_existing_associations

        def write_late(self, *args, **kwargs):
            archive = create_backup(self, *args, **kwargs)
            local.write_text("changed after backup", encoding="utf-8")
            return archive

        monkeypatch.setattr(SnapshotArchiveService, "create_backup_for_existing_associations", write_late)
        with pytest.raises(SourceChangedError, match="changed after backup"):
            catalogue.install_with_result(snapshot, clear_destination=False)
        assert [file.name for file in source.iterdir()] == ["settings.txt"]
        assert local.read_text(encoding="utf-8") == "changed after backup"
    else:
        result = catalogue.install_with_result(snapshot, clear_destination=False)
        assert [file.name for file in source.iterdir() if file.name.casefold() == "settings.txt"] == ["Settings.txt"]
        assert captured.read_text(encoding="utf-8") == "captured"
        assert result.backup_path is not None
        with ZipFile(result.backup_path) as archive:
            member = f"{snapshot.directories[0].directory_name}/settings.txt"
            assert archive.read(member) == b"before merge"
