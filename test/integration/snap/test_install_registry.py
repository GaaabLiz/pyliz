"""Installed-destination history remains scoped to the current snapshot ID."""

from pathlib import Path

import pytest

from pylizlib.core.os.snap import SnapshotCatalogue, SnapshotSettings


def test_reusing_deleted_snapshot_id_does_not_reuse_installed_paths(snapshot_workspace: Path) -> None:
    """A new snapshot cannot automatically remove paths installed by its deleted predecessor."""
    old_target = snapshot_workspace / "old-target"
    old_target.mkdir()
    (old_target / "old.txt").write_text("old installation", encoding="utf-8")
    new_source = snapshot_workspace / "new-source"
    new_source.mkdir()
    (new_source / "new.txt").write_text("new snapshot", encoding="utf-8")
    catalogue = SnapshotCatalogue(
        snapshot_workspace / "catalogue",
        SnapshotSettings(backup_path=snapshot_workspace / "backups"),
    )

    old_snapshot = catalogue.create_snapshot(snap_id="reused", name="Old", directory_paths=[old_target])
    catalogue.install(old_snapshot)
    catalogue.delete(old_snapshot)
    assert old_target.is_dir()

    new_snapshot = catalogue.create_snapshot(snap_id="reused", name="New", directory_paths=[new_source])
    assert catalogue.get_removable_paths(new_snapshot.id) == []
    result = catalogue.remove_installed_copies_with_result(new_snapshot.id)

    assert result.backup_path is None
    assert old_target.is_dir()


def test_remove_rejects_destinations_installed_after_confirmation(snapshot_workspace: Path) -> None:
    first = snapshot_workspace / "first"
    second = snapshot_workspace / "second"
    for path in (first, second):
        path.mkdir()
        (path / "payload").write_text(path.name, encoding="utf-8")
    backups = snapshot_workspace / "backups"
    settings = SnapshotSettings(backup_path=backups)
    catalogue = SnapshotCatalogue(snapshot_workspace / "catalogue", settings)
    other_instance = SnapshotCatalogue(catalogue.path_catalogue, settings)
    snapshot = catalogue.create_snapshot(snap_id="shared", name="Shared", directory_paths=[first])
    catalogue.install(snapshot)
    confirmed = catalogue.get_removable_paths(snapshot.id)
    assert confirmed == [first]

    updated = other_instance.update_snapshot(snapshot.id, directory_paths=[second])
    other_instance.install(updated)
    with pytest.raises(ValueError, match="installed folders changed"):
        catalogue.remove_installed_copies_with_result(snapshot.id, expected_paths=confirmed)

    assert first.is_dir()
    assert second.is_dir()
    assert not backups.exists()

    refreshed = catalogue.get_removable_paths(snapshot.id)
    assert refreshed is not None and set(refreshed) == {first, second}
    assert catalogue.remove_installed_copies_with_result(snapshot.id, expected_paths=refreshed).backup_path is not None
    assert not first.exists()
    assert not second.exists()
