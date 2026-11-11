"""Snapshot backup creation and catalogue restore operations."""

import os
import stat
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from pylizlib.core.data.gen import gen_random_string
from pylizlib.core.log.pylizLogger import logger
from pylizlib.core.os.snap.domain import BackupType, SnapDirAssociation, Snapshot, SnapshotBackupInfo, SnapshotSettings
from pylizlib.core.os.snap.operations.backup_names import build_backup_filename, parse_backup_filename
from pylizlib.core.os.snap.serializer import SnapshotSerializer
from pylizlib.core.os.snap.storage.archives import extract_zip, write_verified_zip
from pylizlib.core.os.snap.storage.context import SnapshotStorage
from pylizlib.core.os.snap.storage.paths import get_snapshot_json_path, get_snapshot_path
from pylizlib.core.os.snap.storage.publication import publish_snapshot_tree
from pylizlib.core.os.snap.storage.transactions import SnapshotTransactionJournal, recover_pending_transactions, recover_storage_transactions, rename_and_sync
from pylizlib.core.os.snap.storage.tree import assert_no_symlinks, iter_tree_entries_strict


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

            zip_name = build_backup_filename(self.storage.snapshot.id, prefix, backup_type, timestamp, is_export)

            backup_path.mkdir(parents=True, exist_ok=True)
            zip_path = backup_path.joinpath(zip_name)

            return write_verified_zip(zip_path, self._files_to_archive(backup_type), message_callback)
        except Exception as e:
            logger.error(f"Failed to create backup for snapshot '{self.storage.snapshot.id}': {e}")
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
        Returns metadata for every .zip backup in the provided folder.

        Args:
            backup_dir: Folder containing backup archives.

        Returns:
            A list of parsed backup metadata entries sorted by date (newest first).
        """
        if not backup_dir.exists() or not backup_dir.is_dir():
            raise ValueError(f"Provided backup directory '{backup_dir}' is not a valid folder.")

        backups: list[SnapshotBackupInfo] = []
        for zip_path in backup_dir.glob("*.zip"):
            backups.append(self.parse_info(zip_path))

        return sorted(
            backups,
            key=lambda b: (b.created_at is not None, b.created_at or datetime.min, b.file_name),
            reverse=True,
        )

    def restore_backup(self, backup_zip_path: Path):
        """
        Restores a backup archive, auto-detecting the backup type from its filename.

        - `_sd` backups restore the whole snapshot directory into the catalogue.
        - `_ad` backups restore associated directories to their `original_path`.

        Args:
            backup_zip_path: Path of the backup .zip archive.

        Raises:
            ValueError: If the archive path is invalid, backup naming is not recognized,
                        or the restore cannot be performed.
            SnapshotIncompleteError: If any expected associated directory is missing
                from an associated-directories archive. Inspect ``missing_folders``.
            IOError: If extraction fails.
        """
        recover_pending_transactions(self.path_catalogue)
        if not backup_zip_path.is_file() or backup_zip_path.suffix != ".zip":
            raise ValueError(f"Provided path '{backup_zip_path}' is not a valid .zip file.")

        info = self.parse_info(backup_zip_path)
        if info.backup_type is None:
            raise ValueError("Could not recognize backup type from filename. Expected suffix '_ad' or '_sd' before timestamp.")

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            extract_zip(backup_zip_path, temp_dir_path)

            if info.backup_type == BackupType.SNAPSHOT_DIRECTORY:
                self._restore_snapshot_directory(temp_dir_path)
                return

            self._restore_associated_directories(info, temp_dir_path)

    def delete_backup(self, backup_zip_path: Path):
        """
        Deletes a backup archive from the filesystem.

        Args:
            backup_zip_path: Path of the backup .zip archive to delete.

        Raises:
            ValueError: If the path is not a valid .zip file or does not exist.
        """
        if not backup_zip_path.is_file() or backup_zip_path.suffix != ".zip":
            raise ValueError(f"Provided path '{backup_zip_path}' is not a valid .zip file.")
        backup_zip_path.unlink()

    def _restore_snapshot_directory(self, temp_dir_path: Path) -> None:
        """Replace a complete snapshot root, preserving the existing restore errors."""
        json_path = temp_dir_path / self.settings.json_filename
        if not json_path.is_file():
            raise ValueError(f"Snapshot-directory backup does not contain '{self.settings.json_filename}'.")

        restored_snapshot = SnapshotSerializer.from_json(json_path)
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

    def _restore_associated_directories(self, info: SnapshotBackupInfo, temp_dir_path: Path) -> None:
        """Restore matching live targets sequentially with their original rollback.

        This is intentionally distinct from installation: it does not introduce
        staging of all copies, new integrity checks, or new destination policy.
        """
        # ASSOCIATED_DIRECTORIES restore
        if not info.snapshot_id:
            raise ValueError("Could not determine snapshot ID from associated-directories backup filename.")

        snapshot = self.lookup.get_by_id(info.snapshot_id)
        if not snapshot:
            raise ValueError(f"Snapshot with ID '{info.snapshot_id}' not found. Associated-directories restore requires an existing snapshot metadata entry.")

        snapshot_root = get_snapshot_path(snapshot.folder_name, self.path_catalogue)
        storage = SnapshotStorage(
            snapshot,
            self.settings,
            self.path_catalogue,
            snapshot_root,
            get_snapshot_json_path(snapshot.folder_name, self.path_catalogue, self.settings.json_filename),
        )
        recover_storage_transactions(storage)

        dir_name_to_assoc: dict[str, SnapDirAssociation] = {assoc.directory_name: assoc for assoc in snapshot.directories}
        extracted_entries = sorted(temp_dir_path.iterdir(), key=lambda entry: entry.name)
        extracted_by_name = {entry.name: entry for entry in extracted_entries}
        missing_folders = [
            association.original_path
            for association in snapshot.directories
            if association.directory_name not in extracted_by_name or not extracted_by_name[association.directory_name].is_dir()
        ]
        unexpected_entries = [entry.name for entry in extracted_entries if entry.name not in dir_name_to_assoc or not entry.is_dir()]

        if not snapshot.directories and not extracted_entries:
            raise ValueError("No associated directories were restored from the backup archive.")
        if missing_folders or unexpected_entries:
            raise SnapshotIncompleteError("Associated-directories restore", missing_folders, unexpected_entries)

        # Preflight the complete set before creating a journal or staging files.
        tasks = []
        for candidate in snapshot.directories:
            extracted_dir = extracted_by_name[candidate.directory_name]
            destination = Path(os.path.abspath(candidate.original_path))
            backup_dest = destination.with_name(f"{destination.name}_bck_{gen_random_string(6)}")
            try:
                destination.lstat()
                had_original = True
            except FileNotFoundError:
                had_original = False
            tasks.append(RestoreReplacement(candidate.folder_id, extracted_dir, destination, backup_dest, had_original))

        journal = SnapshotTransactionJournal.begin(snapshot_root, "restore_associations", {"entries": []})
        try:
            entries = []
            staged_tasks = []
            for index, task in enumerate(tasks):
                staged_dir = journal.workspace / f"restore_{index}"
                assert_no_symlinks(task.staged_dir)
                self.settings.copy_strategy.copy_directory(task.staged_dir, staged_dir)
                assert_no_symlinks(staged_dir)
                staged_task = RestoreReplacement(task.folder_id, staged_dir, task.destination, task.backup_dest, task.had_original)
                staged_tasks.append(staged_task)
                entries.append(
                    {
                        "folder_id": task.folder_id,
                        "stage": staged_dir.as_posix(),
                        "stage_root": journal.workspace.as_posix(),
                        "destination": task.destination.as_posix(),
                        "backup": task.backup_dest.as_posix(),
                        "had_original": task.had_original,
                    }
                )
            tasks = staged_tasks
            journal.update_payload(entries=entries)
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
                journal.decide_rollback(storage)
            except Exception as rollback_error:
                e.add_note(f"Persistent recovery journal retained at '{journal.path}': {rollback_error}")
            raise IOError(f"Failed to restore associated directories: {e}") from e

        journal.finalize([task.backup_dest for task in tasks], "Associated-directories restore")
