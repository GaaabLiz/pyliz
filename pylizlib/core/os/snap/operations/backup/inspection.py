"""Identify backup format and precedence without extracting archive contents."""

import json
import zipfile
from collections.abc import Callable
from pathlib import Path

from pylizlib.core.os.snap.domain import BackupType, SnapshotBackupInfo, SnapshotSettings, validate_directory_component
from pylizlib.core.os.snap.operations.archives import _ArchiveMetadata
from pylizlib.core.os.snap.operations.backup.manifest import parse_legacy_associations_manifest
from pylizlib.core.os.snap.operations.backup_manifest import BACKUP_MANIFEST_NAME, parse_backup_manifest
from pylizlib.core.os.snap.operations.backup_manifest import LEGACY_ASSOCIATED_DIRECTORIES_MANIFEST as ASSOCIATED_DIRECTORIES_MANIFEST


class BackupArchiveInspector:
    """Read embedded identities first, preserving strict modern-manifest precedence."""

    def __init__(self, settings: SnapshotSettings, parse_info: Callable[[Path], SnapshotBackupInfo]):
        """Bind metadata naming and the caller's legacy filename parser.

        Args:
            settings (SnapshotSettings): Live settings defining the JSON member name.
            parse_info (Callable[[Path], SnapshotBackupInfo]): Legacy filename hook;
                embedded identities take precedence over its ID and backup type.

        Returns:
            None: No archive is opened until read is called.
        """
        self.settings = settings
        self.parse_info = parse_info

    def read(self, backup_zip_path: Path) -> _ArchiveMetadata:
        """Read archive identity and type from embedded metadata, falling back for legacy ZIPs."""
        try:
            with zipfile.ZipFile(backup_zip_path, "r") as archive:
                names = archive.namelist()
                if BACKUP_MANIFEST_NAME in names:
                    if names.count(BACKUP_MANIFEST_NAME) != 1:
                        raise ValueError("Snapshot backup archive contains duplicate backup manifests.")
                    try:
                        manifest_data = json.loads(archive.read(BACKUP_MANIFEST_NAME).decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError) as error:
                        raise ValueError(f"Snapshot backup manifest is invalid: {error}") from error
                    manifest = parse_backup_manifest(manifest_data)
                    info = SnapshotBackupInfo(
                        backup_zip_path,
                        backup_zip_path.name,
                        manifest.snapshot_id,
                        manifest.backup_type,
                        manifest.prefix,
                        manifest.created_at,
                        manifest.is_export,
                    )
                    return _ArchiveMetadata(info, manifest.associations, manifest.os_created, BACKUP_MANIFEST_NAME)

                if ASSOCIATED_DIRECTORIES_MANIFEST in names:
                    if names.count(ASSOCIATED_DIRECTORIES_MANIFEST) != 1:
                        raise ValueError("Associated-directories archive contains duplicate legacy manifests.")
                    try:
                        legacy_data = json.loads(archive.read(ASSOCIATED_DIRECTORIES_MANIFEST).decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError) as error:
                        raise ValueError(f"Associated-directories manifest is invalid: {error}") from error
                    snapshot_id, origin_os, associations = parse_legacy_associations_manifest(legacy_data)
                    filename_info = self.parse_info(backup_zip_path)
                    info = self._replace_info_identity(filename_info, snapshot_id, BackupType.ASSOCIATED_DIRECTORIES)
                    return _ArchiveMetadata(info, tuple(associations), origin_os, ASSOCIATED_DIRECTORIES_MANIFEST)

                if self.settings.json_filename in names:
                    if names.count(self.settings.json_filename) != 1:
                        raise ValueError("Snapshot-directory archive contains duplicate snapshot metadata files.")
                    try:
                        snapshot_data = json.loads(archive.read(self.settings.json_filename).decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError) as error:
                        raise ValueError(f"Snapshot-directory metadata is invalid: {error}") from error
                    if not isinstance(snapshot_data, dict) or not isinstance(snapshot_data.get("id"), str) or not snapshot_data["id"]:
                        raise ValueError("Snapshot-directory metadata has no snapshot ID.")
                    validate_directory_component(snapshot_data["id"], "backup snapshot ID")
                    origin_os = snapshot_data.get("os_created")
                    if origin_os is not None and (not isinstance(origin_os, str) or not origin_os):
                        raise ValueError("Snapshot-directory metadata contains an invalid originating OS.")
                    filename_info = self.parse_info(backup_zip_path)
                    info = self._replace_info_identity(filename_info, snapshot_data["id"], BackupType.SNAPSHOT_DIRECTORY)
                    return _ArchiveMetadata(info, None, origin_os)
        except zipfile.BadZipFile:
            # Preserve the legacy error mapping: extraction reports malformed ZIPs.
            return _ArchiveMetadata(self.parse_info(backup_zip_path))
        except ValueError:
            raise
        except Exception as error:
            raise IOError(f"Failed to inspect backup archive '{backup_zip_path}': {error}") from error

        return _ArchiveMetadata(self.parse_info(backup_zip_path))

    @staticmethod
    def _replace_info_identity(info: SnapshotBackupInfo, snapshot_id: str, backup_type: BackupType) -> SnapshotBackupInfo:
        """Retain filename-only convenience fields while replacing ID and type from archive data."""
        return SnapshotBackupInfo(info.path, info.file_name, snapshot_id, backup_type, info.prefix, info.created_at, info.is_export)
