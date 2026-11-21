"""Aggregate catalogue metrics from captured manifests and legacy copy metadata."""

import stat
from collections.abc import Iterator
from pathlib import Path
from typing import cast

from pylizlib.core.os.filesystem.tree import iter_tree_entry_stats_strict
from pylizlib.core.os.snap.domain import SnapDirAssociation, Snapshot, SnapshotCatalogueStatistics, SnapshotFileInfo
from pylizlib.core.os.snap.sorting import chronological_key
from pylizlib.core.os.snap.storage.paths import get_snapshot_child_path


def collect_catalogue_statistics(path_catalogue: Path, snapshots: list[Snapshot], backup_count: int | None) -> SnapshotCatalogueStatistics:
    """Collect all content metrics in one pass over the loaded snapshots.

    Args:
        path_catalogue (Path): Catalogue containing the stored association copies.
        snapshots (list[Snapshot]): Validated published snapshots read under the catalogue lock.
        backup_count (int | None): Recognized archive count, or None if skipped.

    Returns:
        SnapshotCatalogueStatistics: Immutable summary of the supplied snapshots and archive count.
    """
    total_size_bytes = file_count = directory_count = 0
    largest_file_key = oldest = newest = None

    for snapshot in snapshots:
        created = snapshot.date_created
        date_key = (chronological_key(created), snapshot.id)
        if oldest is None or date_key < oldest[0]:
            oldest = (date_key, created)
        if newest is None or date_key > newest[0]:
            newest = (date_key, created)

        for association in snapshot.directories:
            for relative_path, size_bytes in _iter_association_entries(path_catalogue, snapshot.id, association):
                if size_bytes is None:
                    directory_count += 1
                    continue
                total_size_bytes += size_bytes
                file_count += 1
                candidate = (size_bytes, snapshot.id, association.folder_id, relative_path)
                if largest_file_key is None or candidate > largest_file_key:
                    largest_file_key = candidate

    largest_file = None
    if largest_file_key is not None:
        size_bytes, snapshot_id, folder_id, relative_path = largest_file_key
        largest_file = SnapshotFileInfo(snapshot_id, folder_id, relative_path, size_bytes)

    return SnapshotCatalogueStatistics(
        catalogue_path=path_catalogue,
        snapshot_count=len(snapshots),
        total_size_bytes=total_size_bytes,
        file_count=file_count,
        directory_count=directory_count,
        largest_file=largest_file,
        oldest_snapshot_date=oldest[1] if oldest is not None else None,
        newest_snapshot_date=newest[1] if newest is not None else None,
        backup_count=backup_count,
    )


def _iter_association_entries(path_catalogue: Path, snapshot_id: str, association: SnapDirAssociation) -> Iterator[tuple[str, int | None]]:
    """Enumerate captured sizes, falling back to a metadata-only scan for legacy copies.

    Args:
        path_catalogue (Path): Catalogue containing the published snapshot.
        snapshot_id (str): ID of the published snapshot.
        association (SnapDirAssociation): Validated association with its persisted storage name.

    Yields:
        tuple[str, int | None]: Association-relative POSIX path and file size in bytes. Directory sizes are None
            and the association root is included as a directory.
    """
    manifest = association.integrity_manifest
    if manifest is not None:
        for relative_path, entry in manifest.items():
            yield relative_path, cast(int, entry["size"]) if entry["type"] == "file" else None
        return

    root = get_snapshot_child_path(snapshot_id, path_catalogue, association.directory_name)
    yield ".", None
    for path, entry_stat in iter_tree_entry_stats_strict(root):
        yield path.relative_to(root).as_posix(), entry_stat.st_size if stat.S_ISREG(entry_stat.st_mode) else None
