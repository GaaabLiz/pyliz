"""Filesystem catalogue scanning with the original tolerant/strict error policy."""

import stat
from pathlib import Path

from pylizlib.core.log.pylizLogger import logger
from pylizlib.core.os.snap.domain import Snapshot, SnapshotSettings
from pylizlib.core.os.snap.storage.metadata import get_snapshot_from_path
from pylizlib.core.os.snap.storage.paths import get_snapshot_path
from pylizlib.core.os.snap.storage.transactions import TRANSACTION_DIRECTORY


def _is_operational_directory(name: str) -> bool:
    """Identify catalogue-root transaction, staging and backup containers.

    Args:
        name (str): Attribute or filesystem-entry name inspected by this operation.

    Returns:
        bool: Whether a name belongs to transaction, staging or backup storage excluded from catalogue entries.
    """
    return name == TRANSACTION_DIRECTORY or name.startswith("_staging_") or "_staging_" in name or "_bck_" in name


def read_snapshot_by_id(path_catalogue: Path, snap_id: str, settings: SnapshotSettings) -> Snapshot | None:
    """Load one published snapshot directly, without scanning the catalogue.

    Args:
        path_catalogue (Path): Catalogue root retained by this collaborator.
        snap_id (str): Snapshot ID identifying the catalogue entry, rather than its display name.
        settings (SnapshotSettings): Mutable snapshot settings retained by reference; no defensive copy is made.

    Returns:
        Snapshot | None: Matching metadata model or None for an invalid ID, missing tree, parse/I/O failure or ID
            mismatch.
    """
    if not isinstance(snap_id, str) or not snap_id or _is_operational_directory(snap_id):
        return None
    try:
        snapshot_path = get_snapshot_path(snap_id, path_catalogue)
        if not snapshot_path.is_dir():
            return None
        snapshot = get_snapshot_from_path(snapshot_path, settings.json_filename)
        if snapshot is None or snapshot.id != snap_id:
            logger.error(f"Skipping snapshot directory '{snapshot_path}': metadata ID does not match the requested ID '{snap_id}'.")
            return None
        return snapshot
    except Exception as error:
        logger.error(f"Failed to load snapshot '{snap_id}' from '{path_catalogue}': {error}.")
        return None


def read_catalogue(path_catalogue: Path, settings: SnapshotSettings, *, strict: bool = False) -> list[Snapshot]:
    """Retrieves all snapshots from the catalogue.

    Args:
        path_catalogue (Path): Catalogue root retained by this collaborator.
        settings (SnapshotSettings): Mutable snapshot settings retained by reference; no defensive copy is made.
        strict (bool): Propagate filesystem errors instead of skipping unreadable entries.

    Returns:
        list[Snapshot]: A list of Snapshot objects found in the catalogue.
    """
    path_catalogue.mkdir(parents=True, exist_ok=True)
    snapshots: list[Snapshot] = []
    for current_dir in path_catalogue.iterdir():
        if _is_operational_directory(current_dir.name):
            continue
        is_directory = stat.S_ISDIR(current_dir.stat().st_mode) if strict else current_dir.is_dir()
        if is_directory:
            try:
                snap = get_snapshot_from_path(current_dir, settings.json_filename)
                if snap is not None:
                    if current_dir.name != snap.id:
                        logger.error(f"Skipping snapshot directory '{current_dir}': metadata ID '{snap.id}' does not match its directory name.")
                        continue
                    snapshots.append(snap)
            except Exception as e:
                if strict and isinstance(e, OSError):
                    raise
                logger.error(f"Failed to load snapshot from {current_dir}: {e}. Skipping corrupted entry.")
    return snapshots
