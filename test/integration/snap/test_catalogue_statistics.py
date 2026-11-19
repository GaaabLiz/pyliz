"""Catalogue statistics across capture, deletion, backup and synchronization."""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from pylizlib.core.os.snap import SnapDirAssociation, Snapshot, SnapshotCatalogue, SnapshotFileInfo, SnapshotManager, SnapshotSettings


def test_catalogue_statistics_follow_published_changes(snapshot_workspace: Path) -> None:
    """Aggregate the persisted copies and refresh the summary after each operation."""
    settings = SnapshotSettings(backup_path=snapshot_workspace / "backups", backup_pre_delete=True)
    catalogue = SnapshotCatalogue(snapshot_workspace / "catalogue", settings)
    source = snapshot_workspace / "source"
    (source / "nested" / "empty").mkdir(parents=True)
    (source / "shared.txt").write_bytes(b"abc")
    largest = source / "nested" / "large.bin"
    largest.write_bytes(b"123456")
    first = Snapshot("first", "First capture", "", directories=[SnapDirAssociation(0, str(source), "first-source")], date_created=datetime(2024, 1, 1))
    catalogue.add(first)

    largest.write_bytes(b"1234567")
    (source / "zero.txt").touch()
    empty_source = snapshot_workspace / "empty-source"
    empty_source.mkdir()
    second = Snapshot(
        "second",
        "Second capture",
        "",
        directories=[SnapDirAssociation(0, str(source), "second-source"), SnapDirAssociation(1, str(empty_source), "empty-source")],
        date_created=datetime(2024, 1, 3, tzinfo=UTC),
    )
    catalogue.add(second)

    with patch("pylizlib.core.os.snap.operations.statistics.iter_tree_entry_stats_strict", side_effect=AssertionError("captured tree scanned")):
        stats = catalogue.get_statistics()

    assert stats.catalogue_path == catalogue.path_catalogue
    assert stats.snapshot_count == 2
    assert stats.total_size_bytes == 19
    assert stats.average_snapshot_size_bytes == 9.5
    assert stats.file_count == 5
    assert stats.directory_count == 7
    assert stats.largest_file == SnapshotFileInfo("second", "second-source", "nested/large.bin", 7)
    assert stats.oldest_snapshot_date == first.date_created
    assert stats.newest_snapshot_date == second.date_created
    assert stats.backup_count == 0

    catalogue.delete(second)
    after_delete = catalogue.get_statistics()
    assert after_delete.snapshot_count == 1
    assert after_delete.total_size_bytes == 9
    assert after_delete.backup_count == catalogue.get_backup_count() == 1

    SnapshotManager(first, catalogue.path_catalogue, settings).update_associated_dirs_from_system()
    after_sync = catalogue.get_statistics()
    assert after_sync.total_size_bytes == 10
    assert after_sync.file_count == 3
    assert after_sync.directory_count == 3
    assert after_sync.largest_file == SnapshotFileInfo("first", "first-source", "nested/large.bin", 7)
