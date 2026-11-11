"""Snapshot backup creation and catalogue restore operations."""

import json
import os
import stat
import tempfile
import zipfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PureWindowsPath
from typing import Protocol

from pylizlib.core.data.gen import gen_random_string
from pylizlib.core.log.pylizLogger import logger
from pylizlib.core.os.snap.domain import BackupType, Snapshot, SnapshotBackupInfo, SnapshotSettings, validate_directory_component
from pylizlib.core.os.snap.operations.backup_manifest import (
    BACKUP_MANIFEST_NAME,
    LEGACY_ASSOCIATED_DIRECTORIES_MANIFEST,
    LEGACY_ASSOCIATED_DIRECTORIES_MANIFEST_FORMAT,
    ArchivedAssociation,
    build_backup_manifest,
    parse_backup_manifest,
)
from pylizlib.core.os.snap.operations.backup_names import build_backup_filename, parse_backup_filename
from pylizlib.core.os.snap.operations.destinations import validate_destructive_destinations
from pylizlib.core.os.snap.serializer import SnapshotSerializer
from pylizlib.core.os.snap.storage.archives import _write_verified_zip_exclusive, extract_zip
from pylizlib.core.os.snap.storage.context import SnapshotStorage
from pylizlib.core.os.snap.storage.paths import get_snapshot_json_path, get_snapshot_path
from pylizlib.core.os.snap.storage.publication import publish_snapshot_tree
from pylizlib.core.os.snap.storage.transactions import SnapshotTransactionJournal, recover_pending_transactions, recover_storage_transactions, rename_and_sync
from pylizlib.core.os.snap.storage.tree import assert_no_symlinks, iter_tree_entries_strict

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
    """Build and verify ZIP backups of one stored snapshot or its live copies."""

    def __init__(self, storage: SnapshotStorage):
        """Bind the snapshot state and current copy/metadata dependencies."""
        self.storage = storage

    def create_backup(self, backup_path: Path, prefix: str, backup_type: "BackupType", is_export: bool = False, message_callback=None) -> Path:
        """
        Creates, verifies and atomically publishes a zip archive of the snapshot's data.
        Failures propagate to the caller so protected operations cannot continue.

        Args:
            backup_path: The directory where the backup zip file will be saved.
            prefix: A prefix for the backup filename.
            backup_type: The type of backup to create (associated directories or the snapshot directory).
            is_export: If True, the filename will be formatted as an export.

        Returns:
            The path of the verified, published archive.

        Raises:
            SnapshotIncompleteError: If any associated source folder is missing or
                ceases to be readable as a directory during enumeration.
        """
        try:
            if backup_type not in (BackupType.ASSOCIATED_DIRECTORIES, BackupType.SNAPSHOT_DIRECTORY):
                raise ValueError(f"Unsupported backup type: {backup_type}")
            recover_storage_transactions(self.storage)
            self.storage.snapshot.validate()
            self.storage.root_path()
            snapshot_json_path = self.storage.child_path(self.storage.settings.json_filename)
            if backup_type == BackupType.SNAPSHOT_DIRECTORY and not snapshot_json_path.is_file():
                raise FileNotFoundError(f"Snapshot metadata '{snapshot_json_path}' is missing.")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            base_zip_name = build_backup_filename(self.storage.snapshot.id, prefix, backup_type, timestamp, is_export)
            archived_roots = (
                [Path(association.original_path) for association in self.storage.snapshot.directories]
                if backup_type == BackupType.ASSOCIATED_DIRECTORIES
                else [self.storage.root_path()]
            )
            self._validate_archive_destination(backup_path / base_zip_name, archived_roots)

            backup_path.mkdir(parents=True, exist_ok=True)

            entries = list(self._files_to_archive(backup_type))
            if any(archive_name == Path(BACKUP_MANIFEST_NAME) for _, archive_name in entries):
                raise ValueError(f"Snapshot content conflicts with reserved backup manifest '{BACKUP_MANIFEST_NAME}'.")
            manifest_path = self._write_backup_manifest(backup_path, backup_type, prefix, is_export, timestamp)
            entries.append((manifest_path, Path(BACKUP_MANIFEST_NAME)))
            try:
                collision_index = 0
                while True:
                    collision_suffix = f"_{collision_index}" if collision_index else ""
                    zip_name = f"{base_zip_name[:-4]}{collision_suffix}.zip"
                    zip_path = backup_path / zip_name
                    if zip_path.exists() or zip_path.is_symlink():
                        collision_index += 1
                        continue
                    try:
                        return _write_verified_zip_exclusive(zip_path, entries, message_callback)
                    except FileExistsError:
                        if not (zip_path.exists() or zip_path.is_symlink()):
                            raise
                        collision_index += 1
            finally:
                if manifest_path is not None:
                    try:
                        manifest_path.unlink(missing_ok=True)
                    except OSError as error:
                        logger.warning(f"Could not remove temporary associated-directories manifest '{manifest_path}': {error}")
        except Exception as e:
            logger.error(f"Failed to create backup for snapshot '{self.storage.snapshot.id}': {e}")
            raise

    @staticmethod
    def _validate_archive_destination(destination: Path, archived_roots: list[Path]) -> None:
        """Reject a ZIP destination inside any tree that the archive enumerates."""
        try:
            resolved_destination = destination.resolve(strict=False)
            resolved_roots = [(root, root.resolve(strict=False)) for root in archived_roots]
        except Exception as error:
            raise ValueError(f"Cannot verify backup destination '{destination}': {error}") from error

        for source_root, resolved_root in resolved_roots:
            if resolved_destination.is_relative_to(resolved_root):
                raise ValueError(f"Backup destination '{destination}' is inside archived source '{source_root}'.")

    def _write_backup_manifest(self, directory: Path, backup_type: BackupType, prefix: str, is_export: bool, timestamp: str) -> Path:
        """Write a temporary typed manifest with identity and associations for either backup type."""
        data = build_backup_manifest(self.storage.snapshot, backup_type, prefix, is_export, timestamp)
        temporary_path = None
        try:
            temporary_file_context = tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=directory,
                prefix=".backup_metadata_",
                suffix=".partial",
                delete=False,
            )
            with temporary_file_context as temporary_file:
                temporary_path = Path(temporary_file.name)
                json.dump(data, temporary_file, ensure_ascii=False, indent=2)
            return temporary_path
        except Exception:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError as error:
                    logger.warning(f"Could not remove unfinished backup manifest '{temporary_path}': {error}")
            raise

    def _files_to_archive(self, backup_type: BackupType):
        """Enumerate stored or live files using their distinct existing link policies."""
        if backup_type == BackupType.ASSOCIATED_DIRECTORIES:
            sources = []
            missing_folders = []
            for association in self.storage.snapshot.directories:
                folder = Path(association.original_path)
                try:
                    mode = folder.stat().st_mode
                except (FileNotFoundError, NotADirectoryError):
                    missing_folders.append(association.original_path)
                    continue
                if not stat.S_ISDIR(mode):
                    missing_folders.append(association.original_path)
                    continue
                sources.append((association, folder))

            if missing_folders:
                raise SnapshotIncompleteError("Associated-directory backup", missing_folders)

            # Enumerate every source before yielding any member to the ZIP writer.
            entries = []
            for association, folder in sources:
                entries.append((folder, Path(association.directory_name)))
                try:
                    for tree_entry in iter_tree_entries_strict(folder):
                        entries.append((tree_entry, Path(association.directory_name) / tree_entry.relative_to(folder)))
                except (FileNotFoundError, NotADirectoryError):
                    missing_folders.append(association.original_path)

            if missing_folders:
                raise SnapshotIncompleteError("Associated-directory backup", missing_folders)

            yield from entries
        else:
            snapshot_root = self.storage.root_path()
            assert_no_symlinks(snapshot_root)
            for tree_entry in iter_tree_entries_strict(snapshot_root):
                yield tree_entry, tree_entry.relative_to(self.storage.path_snapshot)


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

        metadata = self._read_archive_metadata(backup_zip_path)
        info = metadata.info
        if info.backup_type is None:
            raise ValueError("Could not recognize backup type from archive metadata or legacy filename.")

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            extract_zip(backup_zip_path, temp_dir_path)

            if info.backup_type == BackupType.SNAPSHOT_DIRECTORY:
                if destination_mapping is not None:
                    raise ValueError("Destination remapping is only supported for associated-directories backups.")
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
                    snapshot_id, origin_os, associations = self._parse_legacy_associations_manifest(legacy_data)
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

    def _parse_legacy_associations_manifest(
        self,
        data: object,
    ) -> tuple[str, str | None, list[ArchivedAssociation]]:
        """Read a version 1 or 2 AD manifest written before the unified backup format."""
        if (
            not isinstance(data, dict)
            or data.get("format") != LEGACY_ASSOCIATED_DIRECTORIES_MANIFEST_FORMAT
            or type(data.get("version")) is not int
            or data["version"] not in {1, 2}
        ):
            raise ValueError("Unsupported or invalid associated-directories manifest format.")
        origin_os = data.get("os_created")
        if origin_os is not None and (not isinstance(origin_os, str) or not origin_os):
            raise ValueError("Associated-directories manifest contains an invalid originating OS.")
        if data["version"] == 2 and origin_os is None:
            raise ValueError("Associated-directories manifest does not record its originating OS.")
        snapshot_id = data.get("snapshot_id")
        if not isinstance(snapshot_id, str) or not snapshot_id:
            raise ValueError("Associated-directories manifest has no snapshot ID.")
        validate_directory_component(snapshot_id, "backup snapshot ID")
        raw_associations = data.get("associations")
        if not isinstance(raw_associations, list):
            raise ValueError("Associated-directories manifest has no association list.")

        associations = []
        seen_ids = set()
        seen_names = set()
        for raw in raw_associations:
            if not isinstance(raw, dict):
                raise ValueError("Associated-directories manifest entries must be objects.")
            folder_id = raw.get("folder_id")
            index = raw.get("index")
            directory_name = raw.get("directory_name")
            original_path = raw.get("original_path")
            if not isinstance(folder_id, str) or not folder_id:
                raise ValueError("Associated-directories manifest contains an invalid folder ID.")
            if type(index) is not int or index < 0:
                raise ValueError(f"Associated-directories manifest contains an invalid index for '{folder_id}'.")
            validate_directory_component(directory_name, "archive association directory name")
            if directory_name in {BACKUP_MANIFEST_NAME, ASSOCIATED_DIRECTORIES_MANIFEST}:
                raise ValueError("Associated-directories manifest name conflicts with an archived association.")
            if not isinstance(original_path, str) or not original_path or "\x00" in original_path:
                raise ValueError(f"Associated-directories manifest contains an invalid original path for '{folder_id}'.")
            if not Path(original_path).is_absolute() and not PureWindowsPath(original_path).is_absolute():
                raise ValueError(f"Associated-directories manifest path for '{folder_id}' must be absolute.")
            if folder_id in seen_ids or directory_name in seen_names:
                raise ValueError("Associated-directories manifest contains duplicate association identities or names.")
            seen_ids.add(folder_id)
            seen_names.add(directory_name)
            associations.append(ArchivedAssociation(folder_id, index, directory_name, original_path))
        return snapshot_id, origin_os, associations

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
            associations = [
                ArchivedAssociation(association.folder_id, association.index, association.directory_name, association.original_path)
                for association in snapshot.directories
            ]

        self._restore_archived_associations(temp_dir_path, associations, destination_mapping, metadata.manifest_name, origin_os)

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
        mapping = destination_mapping or {}
        if any(not isinstance(folder_id, str) or not folder_id for folder_id in mapping):
            raise TypeError("Destination mapping keys must be non-empty association IDs.")
        unknown_ids = set(mapping) - {association.folder_id for association in associations}
        if unknown_ids:
            raise ValueError(f"Destination mapping contains unknown association IDs: {', '.join(sorted(unknown_ids))}.")

        extracted_entries = sorted(
            (entry for entry in temp_dir_path.iterdir() if entry.name != manifest_name),
            key=lambda entry: entry.name,
        )
        extracted_by_name = {entry.name: entry for entry in extracted_entries}
        missing_folders = [
            association.original_path
            for association in associations
            if association.directory_name not in extracted_by_name or not extracted_by_name[association.directory_name].is_dir()
        ]
        unexpected_entries = [entry.name for entry in extracted_entries if entry.name not in dir_name_to_assoc or not entry.is_dir()]
        if not associations and not extracted_entries:
            raise ValueError("No associated directories were restored from the backup archive.")
        if missing_folders or unexpected_entries:
            raise SnapshotIncompleteError("Associated-directories restore", missing_folders, unexpected_entries)

        destination_inputs = []
        for association in associations:
            extracted_dir = extracted_by_name[association.directory_name]
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

        destinations = validate_destructive_destinations(
            destination_inputs,
            catalogue_path=self.path_catalogue,
            origin_os=origin_os,
            operation="restore associated directories",
        )

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
