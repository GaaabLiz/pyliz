"""Snapshot backup creation and catalogue restore operations."""

import os
import shutil
import tempfile
import zipfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PureWindowsPath
from typing import Protocol

from pylizlib.core.data.gen import gen_random_string
from pylizlib.core.log.pylizLogger import logger
from pylizlib.core.os.snap.domain import BackupType, Snapshot, SnapshotBackupInfo, SnapshotSettings
from pylizlib.core.os.snap.operations.backup_manifest import (
    LEGACY_ASSOCIATED_DIRECTORIES_MANIFEST,
    ArchivedAssociation,
)
from pylizlib.core.os.snap.operations.backup_names import parse_backup_filename
from pylizlib.core.os.snap.operations.destinations import validate_destructive_destinations
from pylizlib.core.os.snap.serializer import SnapshotSerializer
from pylizlib.core.os.snap.storage.archives import extract_zip, validate_zip_archive
from pylizlib.core.os.snap.storage.context import SnapshotStorage
from pylizlib.core.os.snap.storage.paths import get_snapshot_json_path, get_snapshot_path
from pylizlib.core.os.snap.storage.publication import publish_snapshot_tree
from pylizlib.core.os.snap.storage.transactions import SnapshotTransactionJournal, recover_pending_transactions, recover_storage_transactions, rename_and_sync
from pylizlib.core.os.snap.storage.tree import assert_no_symlinks

ASSOCIATED_DIRECTORIES_MANIFEST = LEGACY_ASSOCIATED_DIRECTORIES_MANIFEST


@dataclass(frozen=True)
class _ArchiveMetadata:
    """Interpretation of one backup ZIP, from its manifest or legacy markers."""

    info: SnapshotBackupInfo
    associations: tuple[ArchivedAssociation, ...] | None = None
    os_created: str | None = None
    manifest_name: str | None = None


class SnapshotIncompleteError(ValueError):
    """Raised when an associated-directory backup or restore is incomplete.

    ``missing_folders`` contains original paths that could not be backed up or
    restored. ``unexpected_entries`` contains top-level archive entries that
    do not match any association in the snapshot metadata.
    """

    def __init__(self, operation: str, missing_folders=(), unexpected_entries=()):
        """Store precise missing and unexpected entries for programmatic callers."""
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
    """Compatible backup facade preserving the storage object and clock hook."""

    def __init__(self, storage: SnapshotStorage):
        """Bind the snapshot state and copy/metadata dependencies."""
        self.storage = storage

    def create_backup(self, backup_path: Path, prefix: str, backup_type: "BackupType", is_export: bool = False, message_callback=None) -> Path:
        """Create a verified AD/SD backup using the dedicated creator."""
        from pylizlib.core.os.snap.operations.backup.creation import BackupCreator

        return BackupCreator(self.storage, now=datetime.now).create_backup(backup_path, prefix, backup_type, is_export, message_callback)


class SnapshotLookup(Protocol):
    """Read-only metadata lookup required by associated-directory restore."""

    def get_by_id(self, snap_id: str) -> Snapshot | None:
        """Return a snapshot using the catalogue's existing lookup semantics."""
        ...


@dataclass(frozen=True)
class RestoreReplacement:
    """Durably staged association and its live destination and optional backup."""

    folder_id: str
    staged_dir: Path
    destination: Path
    backup_dest: Path
    had_original: bool


class CatalogueBackupService:
    """List, remove and restore backups without importing the catalogue facade."""

    def __init__(self, path_catalogue: Path, settings: SnapshotSettings, lookup: SnapshotLookup, parse_info: Callable[[Path], SnapshotBackupInfo] = parse_backup_filename):
        """Capture current paths/settings and preserve the facade's parser hook."""
        self.path_catalogue = path_catalogue
        self.settings = settings
        self.lookup = lookup
        self.parse_info = parse_info

    def list_backups(self, backup_dir: Path) -> list[SnapshotBackupInfo]:
        """
        Returns metadata for every valid ZIP archive in the provided folder.

        Args:
            backup_dir: Folder containing backup archives.

        Returns:
            A list of archive metadata entries sorted by date (newest first).
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

    def restore_backup(self, backup_zip_path: Path):
        """
        Restores a backup using the archive manifest, with filename fallback for legacy ZIPs.

        Snapshot-directory archives restore the stored tree into the catalogue.
        Associated-directory archives restore their captured association paths.

        Args:
            backup_zip_path: Path of the backup .zip archive.

        Raises:
            ValueError: If the archive is invalid, its embedded metadata is not
                        supported, or the restore cannot be performed.
            SnapshotIncompleteError: If any expected associated directory is missing
                from an associated-directories archive. Inspect ``missing_folders``.
            IOError: If extraction fails.
        """
        self._restore_backup(backup_zip_path, None)

    def restore_backup_with_mapping(self, backup_zip_path: Path, destination_mapping: Mapping[str, str | Path]) -> None:
        """Restore an AD archive while overriding destinations by association ID.

        The mapping is keyed by the persistent ``folder_id`` recorded in the
        archive manifest. Unmapped associations retain their archived origin
        path. Legacy AD archives can be mapped when their snapshot metadata is
        still present in the catalogue. Mapping is not supported for snapshot-
        directory archives, regardless of their filename.
        """
        if not isinstance(destination_mapping, Mapping):
            raise TypeError("Destination mapping must be a mapping of folder IDs to paths.")
        self._restore_backup(backup_zip_path, destination_mapping)

    def _restore_backup(self, backup_zip_path: Path, destination_mapping: Mapping[str, str | Path] | None) -> None:
        """Validate, extract and dispatch one archive, with optional AD remapping."""
        recover_pending_transactions(self.path_catalogue)
        if not backup_zip_path.is_file():
            raise ValueError(f"Provided path '{backup_zip_path}' is not a file.")

        preflight = validate_zip_archive(
            backup_zip_path,
            max_entries=self.settings.max_archive_entries,
            max_uncompressed_bytes=self.settings.max_archive_uncompressed_bytes,
        )
        metadata = self._read_archive_metadata(backup_zip_path)
        info = metadata.info
        if info.backup_type is None:
            raise ValueError("Could not recognize backup type from archive metadata or legacy filename.")
        if info.backup_type == BackupType.SNAPSHOT_DIRECTORY and destination_mapping is not None:
            raise ValueError("Destination remapping is only supported for associated-directories backups.")

        restore_space_requirements = []
        if info.backup_type == BackupType.ASSOCIATED_DIRECTORIES:
            associations, origin_os = self._associated_restore_context(metadata)
            destinations = self._resolve_restore_destinations(associations, destination_mapping, origin_os)
            for association, destination in zip(associations, destinations, strict=True):
                if not destination.parent.is_dir():
                    raise FileNotFoundError(f"Parent directory for restore destination '{destination}' does not exist.")
                required_bytes = preflight.bytes_by_root.get(association.directory_name, 0)
                restore_space_requirements.append((destination.parent, required_bytes))
        else:
            restore_space_requirements.append((self.path_catalogue, preflight.uncompressed_bytes))

        temp_parent = self.settings.archive_temp_directory
        if temp_parent is None and info.backup_type == BackupType.ASSOCIATED_DIRECTORIES and destinations:
            # Put the extracted archive on a destination volume by default so a
            # large AD restore does not need equivalent space under system temp.
            temp_parent = max((destination.parent for destination in destinations), key=lambda path: shutil.disk_usage(path).free)
        if temp_parent is None:
            temp_parent = self.path_catalogue
        temp_parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".archive_staging_", dir=temp_parent) as temp_dir:
            temp_dir_path = Path(temp_dir)
            extract_zip(
                backup_zip_path,
                temp_dir_path,
                max_entries=self.settings.max_archive_entries,
                max_uncompressed_bytes=self.settings.max_archive_uncompressed_bytes,
                additional_space_requirements=restore_space_requirements,
            )

            if info.backup_type == BackupType.SNAPSHOT_DIRECTORY:
                self._restore_snapshot_directory(temp_dir_path, metadata)
                return

            self._restore_associated_directories(metadata, temp_dir_path, destination_mapping)

    def delete_backup(self, backup_zip_path: Path):
        """
        Deletes a backup archive from the filesystem.

        Args:
            backup_zip_path: Path of the backup .zip archive to delete.

        Raises:
            ValueError: If the path is not a valid .zip file or does not exist.
        """
        if not backup_zip_path.is_file() or not zipfile.is_zipfile(backup_zip_path):
            raise ValueError(f"Provided path '{backup_zip_path}' is not a valid backup file.")
        backup_zip_path.unlink()

    def _read_archive_metadata(self, backup_zip_path: Path) -> _ArchiveMetadata:
        """Inspect embedded identity and format without extracting the archive."""
        from pylizlib.core.os.snap.operations.backup.inspection import BackupArchiveInspector

        return BackupArchiveInspector(self.settings, self.parse_info).read(backup_zip_path)

    def _parse_legacy_associations_manifest(self, data: object) -> tuple[str, str | None, list[ArchivedAssociation]]:
        """Read a legacy v1/v2 manifest using the compatibility codec."""
        from pylizlib.core.os.snap.operations.backup.manifest import parse_legacy_associations_manifest

        return parse_legacy_associations_manifest(data)

    def _restore_snapshot_directory(self, temp_dir_path: Path, metadata: _ArchiveMetadata) -> None:
        """Replace a complete snapshot root after checking its embedded identity and associations."""
        json_path = temp_dir_path / self.settings.json_filename
        if not json_path.is_file():
            raise ValueError(f"Snapshot-directory backup does not contain '{self.settings.json_filename}'.")

        restored_snapshot = SnapshotSerializer.from_json(json_path)
        if metadata.info.snapshot_id is not None and restored_snapshot.id != metadata.info.snapshot_id:
            raise ValueError("Snapshot-directory JSON ID does not match the archive metadata.")
        if metadata.associations is not None:
            archived_associations = {(item.folder_id, item.index, item.directory_name) for item in metadata.associations}
            snapshot_associations = {(item.folder_id, item.index, item.directory_name) for item in restored_snapshot.directories}
            if archived_associations != snapshot_associations:
                raise ValueError("Snapshot-directory associations do not match the archive metadata.")
        if metadata.manifest_name is not None:
            (temp_dir_path / metadata.manifest_name).unlink(missing_ok=True)
        try:
            publish_snapshot_tree(
                temp_dir_path,
                restored_snapshot.id,
                self.path_catalogue,
                replace_existing=True,
                copy_strategy=self.settings.copy_strategy,
                operation="Snapshot-directory restore",
            )
        except Exception as e:
            logger.error(f"Failed to restore snapshot directory: {e}. Rolling back.")
            raise IOError(f"Failed to restore snapshot directory: {e}") from e

    def _restore_associated_directories(
        self,
        metadata: _ArchiveMetadata,
        temp_dir_path: Path,
        destination_mapping: Mapping[str, str | Path] | None = None,
    ) -> None:
        """Restore AD contents using embedded associations, or legacy catalogue metadata."""
        associations, origin_os = self._associated_restore_context(metadata)
        self._restore_archived_associations(temp_dir_path, associations, destination_mapping, metadata.manifest_name, origin_os)

    def _associated_restore_context(self, metadata: _ArchiveMetadata) -> tuple[list[ArchivedAssociation], str | None]:
        """Resolve the associations and OS that govern an associated-directory restore."""
        info = metadata.info
        if not info.snapshot_id:
            raise ValueError("Could not determine snapshot ID from associated-directories archive metadata.")

        if metadata.associations is not None:
            origin_os = metadata.os_created
            associations = list(metadata.associations)
            if origin_os is None:
                snapshot = self.lookup.get_by_id(info.snapshot_id)
                if not snapshot:
                    raise ValueError("The archive does not record its originating OS and the snapshot metadata is unavailable.")
                origin_os = snapshot.os_created
        else:
            snapshot = self.lookup.get_by_id(info.snapshot_id)
            if not snapshot:
                raise ValueError(f"Snapshot with ID '{info.snapshot_id}' not found. Legacy associated-directories archives require an existing snapshot metadata entry.")
            snapshot_root = get_snapshot_path(snapshot.folder_name, self.path_catalogue)
            storage = SnapshotStorage(
                snapshot,
                self.settings,
                self.path_catalogue,
                snapshot_root,
                get_snapshot_json_path(snapshot.folder_name, self.path_catalogue, self.settings.json_filename),
            )
            recover_storage_transactions(storage)
            origin_os = snapshot.os_created
            associations = [ArchivedAssociation(association.folder_id, association.index, association.directory_name, association.original_path) for association in snapshot.directories]

        return associations, origin_os

    def _resolve_restore_destinations(
        self,
        associations: list[ArchivedAssociation],
        destination_mapping: Mapping[str, str | Path] | None,
        origin_os: str | None,
    ) -> list[Path]:
        """Validate association mapping and all paths before extraction or replacement."""
        mapping = destination_mapping or {}
        if any(not isinstance(folder_id, str) or not folder_id for folder_id in mapping):
            raise TypeError("Destination mapping keys must be non-empty association IDs.")
        unknown_ids = set(mapping) - {association.folder_id for association in associations}
        if unknown_ids:
            raise ValueError(f"Destination mapping contains unknown association IDs: {', '.join(sorted(unknown_ids))}.")

        destination_inputs = []
        for association in associations:
            raw_destination = mapping.get(association.folder_id, association.original_path)
            if not isinstance(raw_destination, (str, os.PathLike)):
                raise TypeError(f"Restore destination for association '{association.folder_id}' must be a path.")
            destination_value = os.fspath(raw_destination)
            if not isinstance(destination_value, str):
                raise TypeError(f"Restore destination for association '{association.folder_id}' must be a string path.")
            if not destination_value or "\x00" in destination_value:
                raise ValueError(f"Restore destination for association '{association.folder_id}' must be non-empty and contain no NUL characters.")
            if association.folder_id not in mapping and not Path(destination_value).is_absolute():
                if PureWindowsPath(destination_value).is_absolute():
                    raise ValueError(f"Restore destination for association '{association.folder_id}' must be mapped for this platform.")
            destination_inputs.append((association.folder_id, destination_value))

        return validate_destructive_destinations(
            destination_inputs,
            catalogue_path=self.path_catalogue,
            origin_os=origin_os,
            operation="restore associated directories",
        )

    def _restore_archived_associations(
        self,
        temp_dir_path: Path,
        associations: list[ArchivedAssociation],
        destination_mapping: Mapping[str, str | Path] | None,
        manifest_name: str | None,
        origin_os: str | None,
    ) -> None:
        """Preflight and transactionally restore every association to its captured or mapped path."""
        dir_name_to_assoc = {association.directory_name: association for association in associations}
        extracted_entries = sorted(
            (entry for entry in temp_dir_path.iterdir() if entry.name != manifest_name),
            key=lambda entry: entry.name,
        )
        extracted_by_name = {entry.name: entry for entry in extracted_entries}
        missing_folders = [
            association.original_path for association in associations if association.directory_name not in extracted_by_name or not extracted_by_name[association.directory_name].is_dir()
        ]
        unexpected_entries = [entry.name for entry in extracted_entries if entry.name not in dir_name_to_assoc or not entry.is_dir()]
        if not associations and not extracted_entries:
            raise ValueError("No associated directories were restored from the backup archive.")
        if missing_folders or unexpected_entries:
            raise SnapshotIncompleteError("Associated-directories restore", missing_folders, unexpected_entries)

        destinations = self._resolve_restore_destinations(associations, destination_mapping, origin_os)

        tasks = []
        for association, destination in zip(associations, destinations, strict=True):
            extracted_dir = extracted_by_name[association.directory_name]
            if not destination.parent.is_dir():
                raise FileNotFoundError(f"Parent directory for restore destination '{destination}' does not exist.")
            backup_dest = destination.with_name(f"{destination.name}_bck_{gen_random_string(6)}")
            try:
                destination.lstat()
                had_original = True
            except FileNotFoundError:
                had_original = False
            tasks.append(RestoreReplacement(association.folder_id, extracted_dir, destination, backup_dest, had_original))

        staged_paths = []
        for task in tasks:
            staged_dir = task.destination.with_name(f"{task.destination.name}_staging_{gen_random_string(6)}")
            while staged_dir.exists() or staged_dir.is_symlink():
                staged_dir = task.destination.with_name(f"{task.destination.name}_staging_{gen_random_string(6)}")
            backup_dest = task.backup_dest
            while backup_dest.exists() or backup_dest.is_symlink():
                backup_dest = task.destination.with_name(f"{task.destination.name}_bck_{gen_random_string(6)}")
            staged_paths.append((staged_dir, backup_dest))

        journal = SnapshotTransactionJournal.begin(self.path_catalogue, "restore_associations_manifest", {"entries": []})
        try:
            entries = []
            staged_tasks = []
            for task, (staged_dir, backup_dest) in zip(tasks, staged_paths, strict=True):
                entries.append(
                    {
                        "folder_id": task.folder_id,
                        "stage": staged_dir.as_posix(),
                        "destination": task.destination.as_posix(),
                        "backup": backup_dest.as_posix(),
                        "had_original": task.had_original,
                    }
                )
            journal.update_payload(entries=entries)

            for task, (staged_dir, backup_dest) in zip(tasks, staged_paths, strict=True):
                assert_no_symlinks(task.staged_dir)
                self.settings.copy_strategy.copy_directory(task.staged_dir, staged_dir)
                assert_no_symlinks(staged_dir)
                staged_task = RestoreReplacement(task.folder_id, staged_dir, task.destination, backup_dest, task.had_original)
                staged_tasks.append(staged_task)
            tasks = staged_tasks
            for task in tasks:
                destination = task.destination
                backup_dest = task.backup_dest
                if task.had_original:
                    if not (destination.exists() or destination.is_symlink()):
                        raise FileNotFoundError(f"Restore destination '{destination}' disappeared before publication.")
                    rename_and_sync(destination, backup_dest)
                elif destination.exists() or destination.is_symlink():
                    raise FileExistsError(f"Restore destination '{destination}' appeared before publication.")
                rename_and_sync(task.staged_dir, destination)

            journal.set_state("commit_decided")
            journal.set_state("committed")
        except Exception as e:
            logger.error(f"Failed to restore associated directories: {e}. Rolling back.")
            try:
                journal.decide_rollback()
            except Exception as rollback_error:
                e.add_note(f"Persistent recovery journal retained at '{journal.path}': {rollback_error}")
            raise IOError(f"Failed to restore associated directories: {e}") from e

        journal.finalize(
            [path for task in tasks for path in (task.backup_dest, task.staged_dir)],
            "Associated-directories restore",
        )
