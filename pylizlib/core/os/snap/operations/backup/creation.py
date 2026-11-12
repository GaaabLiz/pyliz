"""Collect snapshot backup members and publish verified archives exclusively."""

import json
import stat
import tempfile
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from pylizlib.core.log.pylizLogger import logger
from pylizlib.core.os.archives.zip.publication import write_verified_zip_exclusive as _write_verified_zip_exclusive
from pylizlib.core.os.snap.domain import BackupType
from pylizlib.core.os.snap.operations.archives import SnapshotIncompleteError
from pylizlib.core.os.snap.operations.backup_manifest import BACKUP_MANIFEST_NAME, build_backup_manifest
from pylizlib.core.os.snap.operations.backup_names import build_backup_filename
from pylizlib.core.os.snap.storage.context import SnapshotStorage
from pylizlib.core.os.snap.storage.transactions import recover_storage_transactions
from pylizlib.core.os.snap.storage.tree import assert_no_symlinks, iter_tree_entries_strict


class BackupCreator:
    """Build and verify ZIP backups of one stored snapshot or its live copies."""

    def __init__(self, storage: SnapshotStorage, *, now: Callable[[], datetime] = datetime.now):
        """Bind the snapshot state and clock without reading or copying content.

        Args:
            storage (SnapshotStorage): Live model, layout, copy strategy and serializer.
            now (Callable[[], datetime]): Clock called once for each backup timestamp.

        Returns:
            None: The creator retains both dependencies by reference.
        """
        self.storage = storage
        self.now = now

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
            timestamp = self.now().strftime("%Y%m%d_%H%M%S")

            base_zip_name = build_backup_filename(self.storage.snapshot.id, prefix, backup_type, timestamp, is_export)
            archived_roots = [Path(association.original_path) for association in self.storage.snapshot.directories] if backup_type == BackupType.ASSOCIATED_DIRECTORIES else [self.storage.root_path()]
            self._validate_archive_destination(backup_path / base_zip_name, archived_roots)

            backup_path.mkdir(parents=True, exist_ok=True)

            entries = list(self._files_to_archive(backup_type))
            if any(archive_name == Path(BACKUP_MANIFEST_NAME) for _, archive_name in entries):
                raise ValueError(f"Snapshot content conflicts with reserved backup manifest '{BACKUP_MANIFEST_NAME}'.")
            manifest_path = self._write_backup_manifest(backup_path, backup_type, prefix, is_export, timestamp)
            entries.append((manifest_path, Path(BACKUP_MANIFEST_NAME)))
            try:
                result = self._publish_unique_archive(backup_path, base_zip_name, entries, message_callback)
                logger.info("Created snapshot backup snapshot=%s archive=%s type=%s", self.storage.snapshot.id, result, backup_type.name)
                return result
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

    @staticmethod
    def _publish_unique_archive(backup_path: Path, base_zip_name: str, entries: list[tuple[Path, Path]], message_callback=None) -> Path:
        """Retry only final-name collisions while retaining exclusive publication.

        Args:
            backup_path (Path): Existing directory receiving the verified archive.
            base_zip_name (str): Initial filename, including the .zip suffix.
            entries (list[tuple[Path, Path]]): Fully enumerated sources and member names.
            message_callback (Callable[[str], None] | None): Per-member observer.

        Returns:
            Path: Exclusively published archive, adding numeric suffixes on collision.

        Raises:
            OSError: If publication fails for a reason other than an existing name.
        """
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
