"""Versioned metadata stored inside snapshot backup ZIP archives."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PureWindowsPath

from pylizlib.core.os.snap.domain import BackupType, Snapshot, validate_directory_component

BACKUP_MANIFEST_NAME = ".pyliz_backup_manifest.json"
BACKUP_MANIFEST_FORMAT = "pyliz-snapshot-backup"
BACKUP_MANIFEST_VERSION = 1
LEGACY_ASSOCIATED_DIRECTORIES_MANIFEST = ".pyliz_ad_manifest.json"
LEGACY_ASSOCIATED_DIRECTORIES_MANIFEST_FORMAT = "pyliz-associated-directories"


@dataclass(frozen=True)
class ArchivedAssociation:
    """Association identity and origin path captured when an archive is made."""

    folder_id: str
    index: int
    directory_name: str
    original_path: str


@dataclass(frozen=True)
class BackupArchiveManifest:
    """Validated metadata used to interpret a snapshot backup independently of its filename."""

    snapshot_id: str
    backup_type: BackupType
    prefix: str
    is_export: bool
    created_at: datetime
    os_created: str
    associations: tuple[ArchivedAssociation, ...]
    snapshot_name: str
    snapshot_description: str


def build_backup_manifest(
    snapshot: Snapshot,
    backup_type: BackupType,
    prefix: str,
    is_export: bool,
    timestamp: str,
) -> dict:
    """Create the JSON-compatible manifest shared by AD and SD backups."""
    if backup_type == BackupType.ASSOCIATED_DIRECTORIES:
        type_name = "associated_directories"
    elif backup_type == BackupType.SNAPSHOT_DIRECTORY:
        type_name = "snapshot_directory"
    else:
        raise ValueError(f"Unsupported backup type: {backup_type}")
    if not isinstance(prefix, str):
        raise TypeError("Backup prefix must be a string.")
    if type(is_export) is not bool:
        raise TypeError("Backup export flag must be a boolean.")
    if not isinstance(snapshot.os_created, str) or not snapshot.os_created:
        raise ValueError("Snapshot must record its originating OS before it can be backed up.")
    if not isinstance(timestamp, str):
        raise TypeError("Backup timestamp must be a string.")
    datetime.strptime(timestamp, "%Y%m%d_%H%M%S")

    associations = []
    for association in snapshot.directories:
        if association.directory_name in {BACKUP_MANIFEST_NAME, LEGACY_ASSOCIATED_DIRECTORIES_MANIFEST}:
            raise ValueError(f"Association storage name conflicts with reserved backup manifest '{BACKUP_MANIFEST_NAME}'.")
        associations.append(
            {
                "folder_id": association.folder_id,
                "index": association.index,
                "directory_name": association.directory_name,
                "original_path": association.original_path,
            }
        )

    return {
        "format": BACKUP_MANIFEST_FORMAT,
        "version": BACKUP_MANIFEST_VERSION,
        "backup_type": type_name,
        "snapshot_id": snapshot.id,
        "snapshot_name": snapshot.name,
        "snapshot_description": snapshot.desc,
        "os_created": snapshot.os_created,
        "prefix": prefix,
        "is_export": is_export,
        "created_at": timestamp,
        "associations": associations,
    }


def parse_backup_manifest(data: object) -> BackupArchiveManifest:
    """Validate a parsed JSON manifest and return its typed archive metadata."""
    if (
        not isinstance(data, dict)
        or data.get("format") != BACKUP_MANIFEST_FORMAT
        or type(data.get("version")) is not int
        or data["version"] != BACKUP_MANIFEST_VERSION
    ):
        raise ValueError("Unsupported or invalid snapshot backup manifest format.")

    type_map = {
        "associated_directories": BackupType.ASSOCIATED_DIRECTORIES,
        "snapshot_directory": BackupType.SNAPSHOT_DIRECTORY,
    }
    type_name = data.get("backup_type")
    if not isinstance(type_name, str) or type_name not in type_map:
        raise ValueError("Snapshot backup manifest contains an invalid backup type.")

    snapshot_id = data.get("snapshot_id")
    if not isinstance(snapshot_id, str) or not snapshot_id:
        raise ValueError("Snapshot backup manifest has no snapshot ID.")
    validate_directory_component(snapshot_id, "backup snapshot ID")

    snapshot_name = data.get("snapshot_name")
    snapshot_description = data.get("snapshot_description")
    os_created = data.get("os_created")
    prefix = data.get("prefix")
    is_export = data.get("is_export")
    if not isinstance(snapshot_name, str) or not isinstance(snapshot_description, str):
        raise ValueError("Snapshot backup manifest contains invalid snapshot metadata.")
    if not isinstance(os_created, str) or not os_created:
        raise ValueError("Snapshot backup manifest has no originating OS.")
    if not isinstance(prefix, str) or type(is_export) is not bool:
        raise ValueError("Snapshot backup manifest contains invalid filename metadata.")

    created_at_value = data.get("created_at")
    if not isinstance(created_at_value, str):
        raise ValueError("Snapshot backup manifest has no creation timestamp.")
    try:
        created_at = datetime.strptime(created_at_value, "%Y%m%d_%H%M%S")
    except ValueError as error:
        raise ValueError("Snapshot backup manifest contains an invalid creation timestamp.") from error

    raw_associations = data.get("associations")
    if not isinstance(raw_associations, list):
        raise ValueError("Snapshot backup manifest has no association list.")

    associations = []
    seen_ids = set()
    seen_names = set()
    for raw in raw_associations:
        if not isinstance(raw, dict):
            raise ValueError("Snapshot backup manifest association entries must be objects.")
        folder_id = raw.get("folder_id")
        index = raw.get("index")
        directory_name = raw.get("directory_name")
        original_path = raw.get("original_path")
        if not isinstance(folder_id, str) or not folder_id:
            raise ValueError("Snapshot backup manifest contains an invalid association ID.")
        if type(index) is not int or index < 0:
            raise ValueError(f"Snapshot backup manifest contains an invalid index for '{folder_id}'.")
        validate_directory_component(directory_name, "backup association directory name")
        if directory_name in {BACKUP_MANIFEST_NAME, LEGACY_ASSOCIATED_DIRECTORIES_MANIFEST}:
            raise ValueError("Snapshot backup manifest name conflicts with an association directory.")
        if not isinstance(original_path, str) or not original_path or "\x00" in original_path:
            raise ValueError(f"Snapshot backup manifest contains an invalid original path for '{folder_id}'.")
        if not Path(original_path).is_absolute() and not PureWindowsPath(original_path).is_absolute():
            raise ValueError(f"Snapshot backup manifest path for '{folder_id}' must be absolute.")
        if folder_id in seen_ids or directory_name in seen_names:
            raise ValueError("Snapshot backup manifest contains duplicate association IDs or names.")
        seen_ids.add(folder_id)
        seen_names.add(directory_name)
        associations.append(ArchivedAssociation(folder_id, index, directory_name, original_path))

    return BackupArchiveManifest(
        snapshot_id=snapshot_id,
        backup_type=type_map[type_name],
        prefix=prefix,
        is_export=is_export,
        created_at=created_at,
        os_created=os_created,
        associations=tuple(associations),
        snapshot_name=snapshot_name,
        snapshot_description=snapshot_description,
    )
