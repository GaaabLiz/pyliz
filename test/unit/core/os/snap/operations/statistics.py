"""Unit tests for catalogue statistics from validated snapshot data."""

from datetime import UTC, datetime, timedelta, timezone

from pylizlib.core.os.snap import SnapDirAssociation, Snapshot, SnapshotFileInfo
from pylizlib.core.os.snap.operations.statistics import collect_catalogue_statistics


def test_manifest_statistics_count_each_stored_path_and_break_largest_file_ties(tmp_path):
    """Report the captured trees even when only their metadata is available."""
    manifest = {
        ".": {"type": "directory", "size": 0, "sha256": None},
        "empty": {"type": "directory", "size": 0, "sha256": None},
        "second.txt": {"type": "file", "size": 7, "sha256": "1" * 64},
        "first.txt": {"type": "file", "size": 7, "sha256": "1" * 64},
    }
    association = SnapDirAssociation(0, str(tmp_path / "absent-source"), "source", integrity_manifest=manifest)
    snapshots = [Snapshot("b", "b", "", directories=[association]), Snapshot("a", "a", "", directories=[association])]

    stats = collect_catalogue_statistics(tmp_path / "absent-catalogue", snapshots, backup_count=None)

    assert stats.file_count == 4
    assert stats.directory_count == 4
    assert stats.total_size_bytes == 28
    assert stats.average_snapshot_size_bytes == 14.0
    assert stats.largest_file == SnapshotFileInfo("b", "source", "second.txt", 7)


def test_creation_range_orders_instants_and_retains_the_original_dates(tmp_path):
    """Creation dates support both offset-aware and legacy local timestamps."""
    oldest = datetime(2025, 1, 10, 15, tzinfo=timezone(timedelta(hours=8)))
    newest = datetime(2025, 1, 10, 8, tzinfo=timezone(timedelta(hours=-1)))
    local = datetime(2025, 1, 10, 8, tzinfo=UTC).astimezone().replace(tzinfo=None)
    snapshots = [
        Snapshot("new", "Newest", "", date_created=newest),
        Snapshot("local", "Local", "", date_created=local),
        Snapshot("old", "Oldest", "", date_created=oldest),
    ]

    stats = collect_catalogue_statistics(tmp_path, snapshots, backup_count=0)

    assert stats.oldest_snapshot_date.isoformat() == oldest.isoformat()
    assert stats.newest_snapshot_date.isoformat() == newest.isoformat()
