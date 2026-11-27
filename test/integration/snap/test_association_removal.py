"""Exercise backup verification and recovery for confirmed associated-folder removal."""

from pathlib import Path
from zipfile import ZipFile

import pytest

from pylizlib.core.os.snap import SnapshotCatalogue, SnapshotSettings, SourceChangedError
from pylizlib.core.os.snap.operations import removal
from pylizlib.core.os.snap.operations.archives import SnapshotArchiveService


@pytest.fixture
def confirmed_removal(snapshot_workspace):
    directories = [snapshot_workspace / name for name in ("first", "second")]
    for directory in directories:
        directory.mkdir()
        (directory / "data.txt").write_text("before", encoding="utf-8")
    catalogue = SnapshotCatalogue(snapshot_workspace / "catalogue", SnapshotSettings(backup_path=snapshot_workspace / "backups"))
    snapshot = catalogue.create_snapshot(snap_id="removal", name="Removal", directory_paths=directories)
    confirmed = catalogue.get_associated_paths_for_removal(snapshot.id)
    assert confirmed == directories
    return catalogue, snapshot.id, confirmed


@pytest.mark.parametrize("change", ["same_size_edit", "empty_directory", "deleted_file"])
def test_verification_rolls_back_all_folders_after_post_backup_change(confirmed_removal, monkeypatch, change):
    catalogue, snap_id, confirmed = confirmed_removal
    unchanged, changed = (path / "data.txt" for path in confirmed)
    added = confirmed[1] / "new-empty-folder"
    create_backup = SnapshotArchiveService.create_backup_for_associations

    def change_after_backup(*args, **kwargs):
        archive = create_backup(*args, **kwargs)
        if change == "same_size_edit":
            changed.write_text("latest", encoding="utf-8")
        elif change == "empty_directory":
            added.mkdir()
        else:
            changed.unlink()
        return archive

    monkeypatch.setattr(SnapshotArchiveService, "create_backup_for_associations", change_after_backup)
    with pytest.raises(SourceChangedError, match="Associated folder changed after backup"):
        catalogue.remove_associated_paths(snap_id, expected_paths=confirmed, verify_backup=True)

    assert unchanged.read_text(encoding="utf-8") == "before"
    if change == "same_size_edit":
        assert changed.read_text(encoding="utf-8") == "latest"
    elif change == "empty_directory":
        assert added.is_dir()
    else:
        assert not changed.exists()
    assert catalogue.get_backup_count() == 1
    assert not list(unchanged.parent.parent.glob(".pyliz_removing_*"))


def test_verified_removal_produces_a_restorable_backup(confirmed_removal):
    catalogue, snap_id, confirmed = confirmed_removal
    archive = catalogue.remove_associated_paths(snap_id, expected_paths=confirmed, verify_backup=True)
    assert archive is not None
    assert not any(path.exists() for path in confirmed)
    assert not list(confirmed[0].parent.glob(".pyliz_removing_*"))
    catalogue.restore_backup(archive)
    for path in confirmed:
        assert (path / "data.txt").read_text(encoding="utf-8") == "before"


def test_removal_skips_the_optional_comparison_by_default(confirmed_removal, monkeypatch):
    catalogue, snap_id, confirmed = confirmed_removal

    def unexpected_verification(*args, **kwargs):
        pytest.fail("Removal verified the backup without opting in")

    monkeypatch.setattr(removal, "verify_displaced_sources", unexpected_verification)
    archive = catalogue.remove_associated_paths(snap_id, expected_paths=confirmed)
    assert archive is not None
    assert not any(path.exists() for path in confirmed)
    with ZipFile(archive) as backup:
        files = [name for name in backup.namelist() if name.endswith("/data.txt")]
        assert len(files) == 2
        assert all(backup.read(name) == b"before" for name in files)


def test_next_catalogue_lookup_rolls_back_interrupted_removal(confirmed_removal, monkeypatch):
    catalogue, snap_id, confirmed = confirmed_removal
    rename = removal.rename_and_sync

    class SimulatedInterruption(BaseException):
        pass

    def interrupt_after_rename(source: Path, destination: Path) -> None:
        rename(source, destination)
        raise SimulatedInterruption

    monkeypatch.setattr(removal, "rename_and_sync", interrupt_after_rename)
    with pytest.raises(SimulatedInterruption):
        catalogue.remove_associated_paths(snap_id, expected_paths=confirmed, verify_backup=True)
    assert not confirmed[0].exists()

    other = SnapshotCatalogue(catalogue.path_catalogue, catalogue.settings)
    assert other.get_associated_paths_for_removal(snap_id) == confirmed
    for path in confirmed:
        assert (path / "data.txt").read_text(encoding="utf-8") == "before"
    assert not list(confirmed[0].parent.glob(".pyliz_removing_*"))
