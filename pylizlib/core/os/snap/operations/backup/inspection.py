"""Identify backup format and precedence without extracting archive contents."""

import json
import zipfile
from collections.abc import Callable
from pathlib import Path

from pylizlib.core.log.pylizLogger import logger
from pylizlib.core.os.snap.domain import BackupType, SnapshotBackupInfo, SnapshotSettings, validate_directory_component
from pylizlib.core.os.snap.operations.archives import _ArchiveMetadata
from pylizlib.core.os.snap.operations.backup.manifest import parse_legacy_associations_manifest
from pylizlib.core.os.snap.operations.backup_manifest import BACKUP_MANIFEST_NAME, parse_backup_manifest
from pylizlib.core.os.snap.operations.backup_manifest import LEGACY_ASSOCIATED_DIRECTORIES_MANIFEST as ASSOCIATED_DIRECTORIES_MANIFEST


class BackupArchiveInspector:
    """Read embedded identities first, preserving strict modern-manifest precedence.

    Attributes:
        settings (SnapshotSettings): Mutable snapshot settings retained by reference; no defensive copy is made.
        parse_info (Callable[[Path], SnapshotBackupInfo]): Legacy filename parser hook; embedded metadata
            overrides filename identity and type.
    """

    def __init__(self, settings: SnapshotSettings, parse_info: Callable[[Path], SnapshotBackupInfo]):
        """Bind metadata naming and the caller's legacy filename parser.

        Args:
            settings (SnapshotSettings): Live settings defining the JSON member name.
            parse_info (Callable[[Path], SnapshotBackupInfo]): Legacy filename hook; embedded identities take
                precedence over its ID and backup type.

        Returns:
            None: No archive is opened until read is called.
        """
        self.settings = settings
        self.parse_info = parse_info

    def read(self, backup_zip_path: Path) -> _ArchiveMetadata:
        """Read archive identity and type from embedded metadata, falling back for legacy ZIPs.

        Args:
            backup_zip_path (Path): Backup archive path; embedded metadata takes precedence over legacy filename
                hints.

        Returns:
            _ArchiveMetadata: Archive interpretation using modern manifest, legacy AD metadata, legacy SD JSON, then
                filename fallback in that order.
        """
        try:
            with zipfile.ZipFile(backup_zip_path, "r") as archive:
                names = archive.namelist()
                if BACKUP_MANIFEST_NAME in names:
                    result = self._read_modern_manifest(archive, backup_zip_path, names)
                    logger.debug("Read backup metadata archive=%s format=modern", backup_zip_path)
                    return result

                if ASSOCIATED_DIRECTORIES_MANIFEST in names:
                    result = self._read_legacy_manifest(archive, backup_zip_path, names)
                    logger.debug("Read backup metadata archive=%s format=legacy-ad", backup_zip_path)
                    return result

                if self.settings.json_filename in names:
                    result = self._read_snapshot_metadata(archive, backup_zip_path, names)
                    logger.debug("Read backup metadata archive=%s format=legacy-sd", backup_zip_path)
                    return result

        # Preserve the legacy error mapping: extraction reports malformed ZIPs.
        except zipfile.BadZipFile:
            return _ArchiveMetadata(self.parse_info(backup_zip_path))
        except ValueError:
            raise
        except Exception as error:
            raise IOError(f"Failed to inspect backup archive '{backup_zip_path}': {error}") from error

        return _ArchiveMetadata(self.parse_info(backup_zip_path))

    @staticmethod
    def _replace_info_identity(info: SnapshotBackupInfo, snapshot_id: str, backup_type: BackupType) -> SnapshotBackupInfo:
        """Retain filename-only convenience fields while replacing ID and type from archive data.

        Args:
            info (SnapshotBackupInfo): Filename-derived backup info whose ID/type may be replaced by embedded
                metadata.
            snapshot_id (str): Snapshot ID expected in metadata and used for the destination directory.
            backup_type (BackupType): Whether to archive live associated directories (AD) or the stored snapshot tree
                (SD).

        Returns:
            SnapshotBackupInfo: Backup info retaining filename-derived convenience fields with embedded ID and type
                substituted.
        """
        return SnapshotBackupInfo(info.path, info.file_name, snapshot_id, backup_type, info.prefix, info.created_at, info.is_export)

    def _read_modern_manifest(self, archive: zipfile.ZipFile, backup_zip_path: Path, names: list[str]) -> _ArchiveMetadata:
        """Decode the modern identity while retaining format-specific validation.

        Args:
            archive (zipfile.ZipFile): Open ZIP object owned and closed by the surrounding inspection context.
            backup_zip_path (Path): Backup archive path; embedded metadata takes precedence over legacy filename
                hints.
            names (list[str]): Archive member-name list already read from the open ZIP.

        Returns:
            _ArchiveMetadata: Archive metadata containing the unified manifest's authoritative ID, type, origin and
                associations.

        Raises:
            ValueError: A value, path, resource limit or metadata field violates the validation rules described above.
        """
        if names.count(BACKUP_MANIFEST_NAME) != 1:
            raise ValueError("Snapshot backup archive contains duplicate backup manifests.")
        manifest_data = self._read_json_member(archive, BACKUP_MANIFEST_NAME, "Snapshot backup manifest")
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

    def _read_legacy_manifest(self, archive: zipfile.ZipFile, backup_zip_path: Path, names: list[str]) -> _ArchiveMetadata:
        """Decode the legacy-ad identity while retaining format-specific validation.

        Args:
            archive (zipfile.ZipFile): Open ZIP object owned and closed by the surrounding inspection context.
            backup_zip_path (Path): Backup archive path; embedded metadata takes precedence over legacy filename
                hints.
            names (list[str]): Archive member-name list already read from the open ZIP.

        Returns:
            _ArchiveMetadata: Legacy AD association metadata with filename-derived convenience fields.

        Raises:
            ValueError: A value, path, resource limit or metadata field violates the validation rules described above.
        """
        if names.count(ASSOCIATED_DIRECTORIES_MANIFEST) != 1:
            raise ValueError("Associated-directories archive contains duplicate legacy manifests.")
        legacy_data = self._read_json_member(archive, ASSOCIATED_DIRECTORIES_MANIFEST, "Associated-directories manifest")
        snapshot_id, origin_os, associations = parse_legacy_associations_manifest(legacy_data)
        filename_info = self.parse_info(backup_zip_path)
        info = self._replace_info_identity(filename_info, snapshot_id, BackupType.ASSOCIATED_DIRECTORIES)
        return _ArchiveMetadata(info, tuple(associations), origin_os, ASSOCIATED_DIRECTORIES_MANIFEST)

    def _read_snapshot_metadata(self, archive: zipfile.ZipFile, backup_zip_path: Path, names: list[str]) -> _ArchiveMetadata:
        """Decode the legacy-sd identity while retaining format-specific validation.

        Args:
            archive (zipfile.ZipFile): Open ZIP object owned and closed by the surrounding inspection context.
            backup_zip_path (Path): Backup archive path; embedded metadata takes precedence over legacy filename
                hints.
            names (list[str]): Archive member-name list already read from the open ZIP.

        Returns:
            _ArchiveMetadata: Legacy SD identity/origin read from snapshot JSON, with filename convenience fields
                retained.

        Raises:
            ValueError: A value, path, resource limit or metadata field violates the validation rules described above.
        """
        if names.count(self.settings.json_filename) != 1:
            raise ValueError("Snapshot-directory archive contains duplicate snapshot metadata files.")
        snapshot_data = self._read_json_member(archive, self.settings.json_filename, "Snapshot-directory metadata")
        if not isinstance(snapshot_data, dict) or not isinstance(snapshot_data.get("id"), str) or not snapshot_data["id"]:
            raise ValueError("Snapshot-directory metadata has no snapshot ID.")
        validate_directory_component(snapshot_data["id"], "backup snapshot ID")
        origin_os = snapshot_data.get("os_created")
        if origin_os is not None and (not isinstance(origin_os, str) or not origin_os):
            raise ValueError("Snapshot-directory metadata contains an invalid originating OS.")
        filename_info = self.parse_info(backup_zip_path)
        info = self._replace_info_identity(filename_info, snapshot_data["id"], BackupType.SNAPSHOT_DIRECTORY)
        return _ArchiveMetadata(info, None, origin_os)

    @staticmethod
    def _read_json_member(archive: zipfile.ZipFile, member: str, label: str) -> object:
        """Decode one UTF-8 JSON member, preserving the original error category.

        Args:
            archive (zipfile.ZipFile): Open archive owned by the inspection context.
            member (str): Already-recognized metadata member name.
            label (str): Format-specific prefix for a malformed-content error.

        Returns:
            object: Decoded JSON value; each format validates its own schema.

        Raises:
            ValueError: If UTF-8 decoding or JSON parsing fails, with its cause chained.
            OSError: If reading the member fails.
        """
        try:
            return json.loads(archive.read(member).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(f"{label} is invalid: {error}") from error
