"""Snapshot backup creation and catalogue restore operations."""

import shutil
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
from pylizlib.core.os.snap.storage.publication import cleanup_after_commit, publish_snapshot_tree
from pylizlib.core.os.snap.storage.tree import assert_no_symlinks, iter_files_strict


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
        """
        try:
            if backup_type not in (BackupType.ASSOCIATED_DIRECTORIES, BackupType.SNAPSHOT_DIRECTORY):
                raise ValueError(f"Unsupported backup type: {backup_type}")
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
            for d in self.storage.snapshot.directories:
                folder = Path(d.original_path)
                try:
                    mode = folder.stat().st_mode
                except FileNotFoundError:
                    # A missing installation target has no data to protect.
                    continue
                if not stat.S_ISDIR(mode):
                    raise NotADirectoryError(f"Backup source '{folder}' is not a directory.")
                for file_path in iter_files_strict(folder):
                    yield file_path, Path(d.directory_name) / file_path.relative_to(folder)
        else:
            snapshot_root = self.storage.root_path()
            assert_no_symlinks(snapshot_root)
            for file_path in iter_files_strict(snapshot_root):
                yield file_path, file_path.relative_to(self.storage.path_snapshot)


class SnapshotLookup(Protocol):
    """Read-only metadata lookup required by associated-directory restore."""

    def get_by_id(self, snap_id: str) -> Snapshot | None:
        """Return a snapshot using the catalogue's existing lookup semantics."""
        ...


@dataclass(frozen=True)
class RestoreReplacement:
    """Extracted association and its live destination and optional old backup."""

    extracted_dir: Path
    destination: Path
    backup_dest: Path


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
            IOError: If extraction fails.
        """
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

        dir_name_to_assoc: dict[str, SnapDirAssociation] = {assoc.directory_name: assoc for assoc in snapshot.directories}

        # Preflight: collect all targets and validate unambiguously
        tasks = []
        for extracted_dir in temp_dir_path.iterdir():
            if not extracted_dir.is_dir():
                continue

            candidate = dir_name_to_assoc.get(extracted_dir.name)
            if not candidate:
                logger.warning(f"No matching associated directory found for backup folder '{extracted_dir.name}'. Skipping.")
                continue

            destination = Path(candidate.original_path)
            tasks.append(RestoreReplacement(extracted_dir, destination, destination.with_name(f"{destination.name}_bck_{gen_random_string(6)}")))

        if not tasks:
            raise ValueError("No associated directories were restored from the backup archive.")

        # Swap transaction
        completed_rollbacks = []
        try:
            for task in tasks:
                destination = task.destination
                backup_dest = task.backup_dest
                extracted_dir = task.extracted_dir

                if destination.exists():
                    destination.rename(backup_dest)

                self.settings.copy_strategy.copy_directory(extracted_dir, destination)
                completed_rollbacks.append(task)

        except Exception as e:
            logger.error(f"Failed to restore associated directories: {e}. Rolling back.")
            for task in tasks:
                destination = task.destination
                backup_dest = task.backup_dest
                if backup_dest.exists():
                    if destination.exists():
                        shutil.rmtree(destination)
                    backup_dest.rename(destination)
            raise IOError(f"Failed to restore associated directories: {e}") from e

        # All replacements succeeded; backups may now be partially deleted.
        cleanup_after_commit((task.backup_dest for task in tasks), "Associated-directories restore")
