"""Snapshot backup creation and catalogue restore operations."""

import zipfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from pylizlib.core.log.pylizLogger import logger
from pylizlib.core.os.snap.domain import BackupType, Snapshot, SnapshotBackupInfo, SnapshotSettings
from pylizlib.core.os.snap.operations.backup_manifest import (
    LEGACY_ASSOCIATED_DIRECTORIES_MANIFEST,
    ArchivedAssociation,
)
from pylizlib.core.os.snap.operations.backup_names import parse_backup_filename
from pylizlib.core.os.snap.storage.archives import extract_zip, validate_zip_archive
from pylizlib.core.os.snap.storage.context import SnapshotStorage
from pylizlib.core.os.snap.storage.coordination import coordinated

ASSOCIATED_DIRECTORIES_MANIFEST = LEGACY_ASSOCIATED_DIRECTORIES_MANIFEST


@dataclass(frozen=True)
class _ArchiveMetadata:
    """Interpretation of one backup ZIP, from its manifest or legacy markers.

    Attributes:
        info (SnapshotBackupInfo): Normalized backup info, using embedded identity/type before legacy filename
            hints.
        associations (tuple[ArchivedAssociation, ...] | None): Embedded ordered associations, or None when restore
            must consult legacy catalogue metadata.
        os_created (str | None): Embedded origin OS or None when legacy metadata must supply it.
        manifest_name (str | None): Recognized metadata member to exclude from restored content, or None for
            manifest-less legacy backups.

    """

    info: SnapshotBackupInfo
    associations: tuple[ArchivedAssociation, ...] | None = None
    os_created: str | None = None
    manifest_name: str | None = None


class SnapshotIncompleteError(ValueError):
    """Raised when an associated-directory backup or restore is incomplete.

    ``missing_folders`` contains original paths that could not be backed up or
    restored. ``unexpected_entries`` contains top-level archive entries that
    do not match any association in the snapshot metadata.

    Attributes:
        operation (str): Operation name selecting recovery policy or identifying the operation in diagnostics.
        missing_folders (list): Original association paths missing or unreadable as directories; copied into the
            exception list.
        unexpected_entries (list): Unexpected top-level archive names; copied into the exception list.
    """

    def __init__(self, operation: str, missing_folders=(), unexpected_entries=()):
        """Store precise missing and unexpected entries for programmatic callers.

        Args:
            operation (str): Operation name selecting recovery policy or identifying the operation in diagnostics.
            missing_folders (Iterable[str]): Original association paths missing or unreadable as directories; copied
                into the exception list.
            unexpected_entries (Iterable[str]): Unexpected top-level archive names; copied into the exception list.

        Returns:
            None: No return value.
        """
        self.operation = operation
        self.missing_folders = list(missing_folders)
        self.unexpected_entries = list(unexpected_entries)
        details = []
        if self.missing_folders:
            details.append("missing folders: " + ", ".join(self.missing_folders))
        if self.unexpected_entries:
            details.append("unexpected entries: " + ", ".join(self.unexpected_entries))
        super().__init__(f"{operation} is incomplete ({'; '.join(details)}).")


class SnapshotArchiveService:
    """Compatible backup facade preserving the storage object and clock hook.

    Attributes:
        storage (SnapshotStorage): Live snapshot model, settings, captured layout and protected metadata adapter
            for this operation.
    """

    def __init__(self, storage: SnapshotStorage):
        """Bind the snapshot state and copy/metadata dependencies.

        Args:
            storage (SnapshotStorage): Live snapshot model, settings, captured layout and protected metadata adapter
                for this operation.

        Returns:
            None: No return value.
        """
        self.storage = storage

    @coordinated("storage.path_catalogue")
    def create_backup(self, backup_path: Path, prefix: str, backup_type: "BackupType", is_export: bool = False, message_callback=None) -> Path:
        """Create a verified AD/SD backup using the dedicated creator.

        Args:
            backup_path (Path): Directory receiving completed backups and same-directory temporary archive files.
            prefix (str): Backup filename prefix recorded unchanged in the archive manifest.
            backup_type (BackupType): Whether to archive live associated directories (AD) or the stored snapshot tree
                (SD).
            is_export (bool): Whether the backup uses the existing export naming convention.
            message_callback (MessageCallback | None): Optional status observer receiving one message string; its
                exceptions propagate according to the calling operation.

        Returns:
            Path: Verified archive path after exclusive publication, with numeric collision suffixes as needed.

        Raises:
            SnapshotBusyError: Another operation owns the catalogue, or an observer attempts a modifying call.
        """
        from pylizlib.core.os.snap.operations.backup.creation import BackupCreator

        return BackupCreator(self.storage, now=datetime.now).create_backup(backup_path, prefix, backup_type, is_export, message_callback)


class SnapshotLookup(Protocol):
    """Metadata lookup required by AD restore, including the implementation's recovery policy."""

    def get_by_id(self, snap_id: str) -> Snapshot | None:
        """Return a snapshot using the catalogue's existing lookup semantics.

        Args:
            snap_id (str): Snapshot ID identifying the catalogue entry, rather than its display name.

        Returns:
            Snapshot | None: Matching published snapshot, or None for missing, unreadable, invalid or mismatched
                metadata; recovery can raise before tolerant lookup.

        Notes:
            The supplied catalogue implementation may recover pending transactions before lookup; recovery failures
            propagate before tolerant per-entry loading.
        """
        ...


@dataclass(frozen=True)
class RestoreReplacement:
    """Durably staged association and its live destination and optional backup.

    Attributes:
        folder_id (str): Non-empty stable association identity; physical storage uses its digest, so it need not
            be a path component.
        staged_dir (Path): Generated destination-volume copy ready for publication; no longer used to mean
            extracted input in the new restore plan.
        destination (Path): Target path receiving the copied content or metadata.
        backup_dest (Path): Generated sibling retaining the original AD restore destination.
        had_original (bool): Whether planning observed a preexisting target; publication still checks concurrent
            changes.
    """

    folder_id: str
    staged_dir: Path
    destination: Path
    backup_dest: Path
    had_original: bool


class CatalogueBackupService:
    """List, remove and restore backups without importing the catalogue facade.

    Attributes:
        path_catalogue (Path): Catalogue root retained by this collaborator.
        settings (SnapshotSettings): Mutable snapshot settings retained by reference; no defensive copy is made.
        lookup (SnapshotLookup): Catalogue lookup capability used when legacy archive metadata needs a persisted
            snapshot.
        parse_info (Callable[[Path], SnapshotBackupInfo]): Legacy filename parser hook; embedded metadata
            overrides filename identity and type.
    """

    def __init__(self, path_catalogue: Path, settings: SnapshotSettings, lookup: SnapshotLookup, parse_info: Callable[[Path], SnapshotBackupInfo] = parse_backup_filename):
        """Capture current paths/settings and preserve the facade's parser hook.

        Args:
            path_catalogue (Path): Catalogue root retained by this collaborator.
            settings (SnapshotSettings): Mutable snapshot settings retained by reference; no defensive copy is made.
            lookup (SnapshotLookup): Catalogue lookup capability used when legacy archive metadata needs a persisted
                snapshot.
            parse_info (Callable[[Path], SnapshotBackupInfo]): Legacy filename parser hook; embedded metadata
                overrides filename identity and type.

        Returns:
            None: No return value.
        """
        self.path_catalogue = path_catalogue
        self.settings = settings
        self.lookup = lookup
        self.parse_info = parse_info

    def list_backups(self, backup_dir: Path) -> list[SnapshotBackupInfo]:
        """List every file recognized as a ZIP archive, regardless of its filename suffix.

        Args:
            backup_dir (Path): Folder containing backup archives.

        Returns:
            list[SnapshotBackupInfo]: A list of archive metadata entries sorted by date (newest first).

        Raises:
            ValueError: A value, path, resource limit or metadata field violates the validation rules described above.
        """
        if not backup_dir.exists() or not backup_dir.is_dir():
            raise ValueError(f"Provided backup directory '{backup_dir}' is not a valid folder.")

        backups: list[SnapshotBackupInfo] = []
        for zip_path in backup_dir.iterdir():
            if not zip_path.is_file() or not zipfile.is_zipfile(zip_path):
                continue
            try:
                validate_zip_archive(
                    zip_path,
                    max_entries=self.settings.max_archive_entries,
                    max_uncompressed_bytes=self.settings.max_archive_uncompressed_bytes,
                )
                backups.append(self._read_archive_metadata(zip_path).info)
            except Exception as error:
                logger.warning(f"Could not read embedded backup metadata from '{zip_path}': {error}")
                backups.append(SnapshotBackupInfo(zip_path, zip_path.name, None, None, "", None, False))

        return sorted(
            backups,
            key=lambda b: (b.created_at is not None, b.created_at or datetime.min, b.file_name),
            reverse=True,
        )

    @coordinated("path_catalogue")
    def restore_backup(self, backup_zip_path: Path):
        """Restores a backup using the archive manifest, with filename fallback for legacy ZIPs.

        Snapshot-directory archives restore the stored tree into the catalogue.
        Associated-directory archives restore their captured association paths.

        Args:
            backup_zip_path (Path): Path of the backup .zip archive.

        Returns:
            None: No return value.

        Raises:
            SnapshotBusyError: Another operation owns the catalogue, or an observer attempts a modifying call.
            ValueError: If the archive is invalid, its embedded metadata is not supported, or the restore cannot be
                performed.
            SnapshotIncompleteError: If any expected associated directory is missing from an associated-directories
                archive. Inspect ``missing_folders``.
            IOError: If extraction fails.
        """
        self._restore_backup(backup_zip_path, None)

    @coordinated("path_catalogue")
    def restore_backup_with_mapping(self, backup_zip_path: Path, destination_mapping: Mapping[str, str | Path]) -> None:
        """Restore an AD archive while overriding destinations by association ID.

        The mapping is keyed by the persistent ``folder_id`` recorded in the
        archive manifest. Unmapped associations retain their archived origin
        path. Legacy AD archives can be mapped when their snapshot metadata is
        still present in the catalogue. Mapping is not supported for snapshot-
        directory archives, regardless of their filename.

        Args:
            backup_zip_path (Path): Backup archive path; embedded metadata takes precedence over legacy filename
                hints.
            destination_mapping (Mapping[str, str | Path]): Overrides keyed by stable folder_id; unmapped AD
                associations retain their archived source paths.

        Returns:
            None: No return value.

        Raises:
            SnapshotBusyError: Another operation owns the catalogue, or an observer attempts a modifying call.
            TypeError: An argument or mutable model field has a type rejected by this contract.

        Notes:
            Mapping is AD-only and keyed by stable IDs. Unknown IDs are rejected, unmapped IDs retain their origin,
            and origin-OS checks still apply. Archives missing standalone association/origin information require
            catalogue lookup.
        """
        if not isinstance(destination_mapping, Mapping):
            raise TypeError("Destination mapping must be a mapping of folder IDs to paths.")
        self._restore_backup(backup_zip_path, destination_mapping)

    def _restore_backup(self, backup_zip_path: Path, destination_mapping: Mapping[str, str | Path] | None) -> None:
        """Delegate restore while preserving parser and extraction hooks.

        Args:
            backup_zip_path (Path): Backup archive path; embedded metadata takes precedence over legacy filename
                hints.
            destination_mapping (Mapping[str, str | Path] | None): Overrides keyed by stable folder_id; unmapped AD
                associations retain their archived source paths.

        Returns:
            None: No return value.
        """
        from pylizlib.core.os.snap.operations.backup.restore import BackupRestorer

        BackupRestorer(self.path_catalogue, self.settings, self.lookup, self.parse_info, extractor=extract_zip).restore(backup_zip_path, destination_mapping)

    @coordinated("path_catalogue")
    def delete_backup(self, backup_zip_path: Path):
        """Deletes a backup archive from the filesystem.

        Args:
            backup_zip_path (Path): Path of the backup .zip archive to delete.

        Returns:
            None: No return value.

        Raises:
            SnapshotBusyError: Another operation owns the catalogue, or an observer attempts a modifying call.
            ValueError: If the path is absent or is not recognized as a valid ZIP archive.
            OSError: If unlinking the existing archive fails.
        """
        if not backup_zip_path.is_file() or not zipfile.is_zipfile(backup_zip_path):
            raise ValueError(f"Provided path '{backup_zip_path}' is not a valid backup file.")
        backup_zip_path.unlink()

    def _read_archive_metadata(self, backup_zip_path: Path) -> _ArchiveMetadata:
        """Inspect embedded identity and format without extracting the archive.

        Args:
            backup_zip_path (Path): Backup archive path; embedded metadata takes precedence over legacy filename
                hints.

        Returns:
            _ArchiveMetadata: Recognized archive identity and association/origin metadata, using modern-first
                precedence and legacy fallback.
        """
        from pylizlib.core.os.snap.operations.backup.inspection import BackupArchiveInspector

        return BackupArchiveInspector(self.settings, self.parse_info).read(backup_zip_path)

    def _parse_legacy_associations_manifest(self, data: object) -> tuple[str, str | None, list[ArchivedAssociation]]:
        """Read a legacy v1/v2 manifest using the compatibility codec.

        Args:
            data (object): Decoded JSON value or metadata mapping; fields are validated without implicit schema
                coercion.

        Returns:
            tuple[str, str | None, list[ArchivedAssociation]]: Snapshot ID, optional origin OS and ordered legacy
                associations, in that order.
        """
        from pylizlib.core.os.snap.operations.backup.manifest import parse_legacy_associations_manifest

        return parse_legacy_associations_manifest(data)
