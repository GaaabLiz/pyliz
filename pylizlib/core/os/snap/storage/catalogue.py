"""Filesystem catalogue scanning with the original tolerant/strict error policy."""

import stat
from pathlib import Path

from pylizlib.core.log.pylizLogger import logger
from pylizlib.core.os.snap.domain import Snapshot, SnapshotSettings
from pylizlib.core.os.snap.storage.metadata import get_snapshot_from_path
from pylizlib.core.os.snap.storage.transactions import TRANSACTION_DIRECTORY


def _is_operational_directory(name: str) -> bool:
    """Identify catalogue-root transaction, staging and backup containers."""
    return (
        name == TRANSACTION_DIRECTORY
        or name.startswith("_staging_")
        or "_staging_" in name
        or "_bck_" in name
    )


def read_catalogue(path_catalogue: Path, settings: SnapshotSettings, *, strict: bool = False) -> list[Snapshot]:
    """
    Retrieves all snapshots from the catalogue.

    Args:
        strict: Propagate filesystem errors instead of skipping unreadable entries.

    Returns:
        A list of Snapshot objects found in the catalogue.
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
                        logger.error(
                            f"Skipping snapshot directory '{current_dir}': metadata ID '{snap.id}' does not match its directory name."
                        )
                        continue
                    snapshots.append(snap)
            except Exception as e:
                if strict and isinstance(e, OSError):
                    raise
                logger.error(f"Failed to load snapshot from {current_dir}: {e}. Skipping corrupted entry.")
    return snapshots
