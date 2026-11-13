"""Existing backup filename generation and permissive metadata parsing."""

import re
from datetime import datetime
from pathlib import Path

from pylizlib.core.os.snap.domain import BackupType, SnapshotBackupInfo


def build_backup_filename(snapshot_id: str, prefix: str, backup_type: BackupType, timestamp: str, is_export: bool = False) -> str:
    """Build the existing ZIP name without changing ID, prefix or timestamp grammar.

    The operation validates backup_type before calling this naming function.
    Keeping the timestamp as an input preserves its original acquisition point.

    Args:
        snapshot_id (str): Snapshot ID expected in metadata and used for the destination directory.
        prefix (str): Backup filename prefix recorded unchanged in the archive manifest.
        backup_type (BackupType): Whether to archive live associated directories (AD) or the stored snapshot tree
            (SD).
        timestamp (str): Creation timestamp in YYYYMMDD_HHMMSS format using the existing naive/local naming
            convention.
        is_export (bool): Whether the backup uses the existing export naming convention.

    Returns:
        str: ZIP basename using the existing ID/prefix/type/timestamp/export grammar.
    """
    backup_type_suffix = ""
    if backup_type == BackupType.ASSOCIATED_DIRECTORIES:
        backup_type_suffix = "_ad"
    elif backup_type == BackupType.SNAPSHOT_DIRECTORY:
        backup_type_suffix = "_sd"
    if is_export:
        return f"{prefix}_{snapshot_id}{backup_type_suffix}_{timestamp}.zip"
    return f"backup_{prefix}_{snapshot_id}{backup_type_suffix}_{timestamp}.zip"


def parse_backup_filename(backup_path: Path) -> SnapshotBackupInfo:
    """Parse legacy filename hints; embedded manifests are authoritative for new backups.

    Args:
        backup_path (Path): Directory receiving completed backups and same-directory temporary archive files.

    Returns:
        SnapshotBackupInfo: Best-effort filename hints, including legacy collision suffixes; embedded manifests
            remain authoritative.
    """
    stem = backup_path.stem
    created_at = None
    backup_type: BackupType | None = None

    # Expected timestamp suffix: _YYYYMMDD_HHMMSS, optionally followed by a
    # numeric collision suffix selected during exclusive backup publication.
    time_match = re.search(r"_(\d{8}_\d{6})(?:_\d+)?$", stem)
    core = stem
    if time_match:
        time_value = time_match.group(1)
        try:
            created_at = datetime.strptime(time_value, "%Y%m%d_%H%M%S")
        except ValueError:
            created_at = None
        core = stem[: time_match.start()]

    if core.endswith("_ad"):
        backup_type = BackupType.ASSOCIATED_DIRECTORIES
        core = core[:-3]
    elif core.endswith("_sd"):
        backup_type = BackupType.SNAPSHOT_DIRECTORY
        core = core[:-3]

    is_export = not core.startswith("backup_")
    payload = core[7:] if core.startswith("backup_") else core

    prefix = payload
    snapshot_id: str | None = None
    if "_" in payload:
        prefix, snapshot_id = payload.rsplit("_", 1)

    return SnapshotBackupInfo(
        path=backup_path,
        file_name=backup_path.name,
        snapshot_id=snapshot_id,
        backup_type=backup_type,
        prefix=prefix,
        created_at=created_at,
        is_export=is_export,
    )
