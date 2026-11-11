"""
Lifecycle manager for a single Snapshot instance.

Responsibilities (Single Responsibility Principle):
    - Creating, deleting, and duplicating a snapshot on the filesystem.
    - Installing a snapshot's contents to their original target locations.
    - Adding and removing individual directory associations.
    - Applying diff-based edit actions to a snapshot's contents.
    - Synchronising the snapshot's internal copy from live system directories.
    - Creating backup archives of a snapshot's data.

Classes:
    SnapshotManager – Manages all filesystem operations for one Snapshot.
"""

import shutil
import stat
import tempfile
from datetime import datetime
from pathlib import Path

from pylizlib.core.data.gen import gen_random_string
from pylizlib.core.log.pylizLogger import logger
from pylizlib.core.os.path import remove_directory_or_move_to_temp
from pylizlib.core.os.snap.domain import (
    BackupType,
    SnapDirAssociation,
    SnapEditAction,
    Snapshot,
    SnapshotSettings,
    validate_directory_component,
)
from pylizlib.core.os.snap.operations.edits import SnapshotEditor
from pylizlib.core.os.snap.operations.install import SnapshotInstaller
from pylizlib.core.os.snap.serializer import SnapshotSerializer
from pylizlib.core.os.snap.storage.context import SnapshotStorage
from pylizlib.core.os.snap.utils import SnapshotUtils
from pylizlib.core.os.utils import get_folder_size_mb


class SnapshotManager:
    def __init__(
        self,
        snapshot: Snapshot,
        catalogue_path: Path,
        settings: SnapshotSettings = SnapshotSettings(),
    ):
        """
        Initializes a manager for a single snapshot's lifecycle.

        Args:
            snapshot: The `Snapshot` object to manage.
            catalogue_path: The root path of the snapshot catalogue.
            settings: Configuration settings for the manager.
        """
        self.snapshot = snapshot
        self.settings = settings
        self.path_catalogue = catalogue_path
        self.snapshot.validate()
        validate_directory_component(self.settings.json_filename, "Snapshot JSON filename")
        self.path_snapshot = SnapshotUtils.validate_snapshot_root(self.snapshot.folder_name, self.path_catalogue)
        self.path_snapshot_json = SnapshotUtils.get_snapshot_json_path(self.snapshot.folder_name, self.path_catalogue, self.settings.json_filename)

    def _snapshot_root_path(self) -> Path:
        """Validate that the catalogue entry still names this snapshot root."""
        return self._storage().root_path()

    def _snapshot_child_path(self, name: str) -> Path:
        """Return a validated, contained child of this snapshot."""
        return self._storage().child_path(name)

    def __save_json(self):
        """Saves the current snapshot object state to its JSON file."""
        self._storage().save_json()

    def create(self, progress_callback=None, message_callback=None, *, replace_existing: bool = False):
        """
        Creates the snapshot by preparing its contents and metadata in staging.

        Existing IDs are rejected unless replace_existing=True. An explicit
        replacement retains the old directory until publication succeeds and
        restores it if publication fails. Cleanup runs after commit.

        Raises:
            FileExistsError: If the destination exists and replacement is disabled.
        """
        self.snapshot.validate()
        validate_directory_component(self.settings.json_filename, "Snapshot JSON filename")
        self._snapshot_root_path()
        if not replace_existing and (self.path_snapshot.exists() or self.path_snapshot.is_symlink()):
            raise FileExistsError(f"Snapshot destination '{self.path_snapshot}' already exists.")

        self.path_catalogue.mkdir(parents=True, exist_ok=True)
        transaction_path = Path(tempfile.mkdtemp(prefix=f"_staging_create_{self.snapshot.id}_", dir=self.path_catalogue))
        staging_path = transaction_path / "new"
        backup_path = transaction_path / "original"
        original_moved = False
        previous_manifests = {assoc.folder_id: assoc.integrity_manifest for assoc in self.snapshot.directories}
        try:
            staging_path.mkdir()

            # We need to distribute the progress among directories if there are multiple.
            total_dirs = len(self.snapshot.directories)
            for i, snap_dir in enumerate(self.snapshot.directories):

                def dir_progress(copied, total):
                    if progress_callback:
                        # Calculate overall percentage based on dir index and dir progress
                        dir_pct = (copied / total) if total > 0 else 1.0
                        overall_pct = ((i + dir_pct) / total_dirs) * 100
                        progress_callback(int(overall_pct))

                manifest = {}
                snap_dir.copy_install_to(
                    staging_path,
                    progress_callback=dir_progress,
                    message_callback=message_callback,
                    copy_strategy=self.settings.copy_strategy,
                    manifest=manifest,
                )
                snap_dir.integrity_manifest = manifest

            # Write json to staging BEFORE making it the final destination
            json_path = staging_path / validate_directory_component(self.settings.json_filename, "Snapshot JSON filename")
            SnapshotSerializer.to_json(self.snapshot, json_path)

            if self.path_snapshot.exists() or self.path_snapshot.is_symlink():
                if not replace_existing:
                    raise FileExistsError(f"Snapshot destination '{self.path_snapshot}' already exists.")
                self.path_snapshot.rename(backup_path)
                original_moved = True
            staging_path.rename(self.path_snapshot)
        except Exception:
            for assoc in self.snapshot.directories:
                assoc.integrity_manifest = previous_manifests[assoc.folder_id]
            if original_moved:
                # If rollback itself fails, preserve both copies in the
                # transaction directory instead of deleting recoverable data.
                backup_path.rename(self.path_snapshot)
            shutil.rmtree(transaction_path, ignore_errors=True)
            raise

        SnapshotUtils.cleanup_after_commit([transaction_path], "Snapshot creation")

    def delete(self, message_callback=None):
        """
        Deletes the snapshot's directory, propagating filesystem failures.
        """
        remove_directory_or_move_to_temp(self._snapshot_root_path(), message_callback=message_callback)

    def update_json_data_fields(self):
        """
        Updates the 'data' and 'date_last_modified' fields in the snapshot's JSON file.
        This method is typically called after modifying the snapshot's data dictionary.
        """
        self.snapshot.validate()
        json_path = self._snapshot_child_path(self.settings.json_filename)
        SnapshotSerializer.update_field(json_path, "data", self.snapshot.data)
        SnapshotSerializer.update_field(json_path, "date_last_modified", datetime.now().isoformat())
        self.snapshot.date_last_modified = datetime.now()

    def update_json_base_fields(self):
        """
        Updates the basic metadata fields (name, desc, author, tags, date_modified)
        of the snapshot's JSON file.
        """
        self.snapshot.validate()
        json_path = self._snapshot_child_path(self.settings.json_filename)
        SnapshotSerializer.update_field(json_path, "name", self.snapshot.name)
        SnapshotSerializer.update_field(json_path, "desc", self.snapshot.desc)
        SnapshotSerializer.update_field(json_path, "author", self.snapshot.author)
        SnapshotSerializer.update_field(json_path, "tags", self.snapshot.tags)
        SnapshotSerializer.update_field(json_path, "date_modified", datetime.now().isoformat())
        self.snapshot.date_modified = datetime.now()

    def install_directory(self, destination_path: Path):
        """
        Adds a new directory to the snapshot, copying its contents into the
        snapshot's storage directory.

        Args:
            destination_path: The path of the directory to add to the snapshot.

        Raises:
            ValueError: If the destination_path is not a valid directory.
        """
        if not destination_path.exists() or not destination_path.is_dir():
            raise ValueError(f"The provided path {destination_path} is not a valid directory.")
        new_dir = SnapDirAssociation(
            index=SnapDirAssociation.next_index(),
            original_path=destination_path.as_posix(),
            folder_id=gen_random_string(self.settings.folder_id_length),
        )
        manifest = {}
        new_dir.copy_install_to(
            self._snapshot_root_path(),
            copy_strategy=self.settings.copy_strategy,
            manifest=manifest,
        )
        new_dir.integrity_manifest = manifest
        self.snapshot.directories.append(new_dir)
        self.__save_json()

    def uninstall_directory_by_folder_id(self, folder_id: str):
        """
        Removes a directory from the snapshot based on its folder_id.
        This deletes the directory's copy from the snapshot's storage and updates the JSON file.

        Args:
            folder_id: The unique ID of the folder to remove.
        """
        dir_to_remove = next((d for d in self.snapshot.directories if d.folder_id == folder_id), None)
        if dir_to_remove:
            dir_path = self._snapshot_child_path(dir_to_remove.directory_name)
            remove_directory_or_move_to_temp(dir_path)
            self.snapshot.directories.remove(dir_to_remove)
            self.__save_json()

    def update_from_actions_list(self, edits: list[SnapEditAction], message_callback=None):
        """
        Plans edits by association ID against the stored metadata, then stages all
        affected copies before assigning final names. Originals remain available
        for rollback until the updated metadata has been saved.

        Args:
            edits: A list of SnapEditAction objects.
        """
        SnapshotEditor(self._storage()).apply(edits, message_callback=message_callback)

    def duplicate(self, message_callback=None):
        """
        Creates a duplicate of the current snapshot with a new ID and name.
        The entire snapshot directory is copied, and a new JSON file is created for the copy.

        Raises:
            FileNotFoundError: If the original snapshot path does not exist.
        """
        self._snapshot_root_path()
        if not self.path_snapshot.exists():
            raise FileNotFoundError(f"The snapshot path {self.path_snapshot} does not exist.")
        new_snap = self.snapshot.clone()
        new_snap.id = gen_random_string(self.settings.snap_id_length)
        new_snap.name = self.snapshot.name + " Copy"
        new_snap.date_created = datetime.now()

        def prepare_duplicate(staging_path: Path) -> None:
            json_path = staging_path / validate_directory_component(self.settings.json_filename, "Snapshot JSON filename")
            SnapshotSerializer.to_json(new_snap, json_path)

        SnapshotUtils.publish_snapshot_tree(
            self._snapshot_root_path(),
            new_snap.folder_name,
            self.path_catalogue,
            prepare_staging=prepare_duplicate,
            copy_strategy=self.settings.copy_strategy,
            message_callback=message_callback,
            operation="Snapshot duplication",
        )

    def update_associated_dirs_from_system(self, message_callback=None):
        """
        Updates the snapshot's internal copy of each associated directory
        with the current version from the original system path.
        """
        self.snapshot.validate()
        self._snapshot_root_path()
        # 1 & 2. Validate all sources before deleting anything
        for dir_assoc in self.snapshot.directories:
            system_path = Path(dir_assoc.original_path)
            if not system_path.exists() or not system_path.is_dir():
                raise FileNotFoundError(f"Original path '{system_path}' for snapshot '{self.snapshot.id}' does not exist or is not a directory. Update aborted.")

        rollbacks = []
        updated_manifests = {}
        original_metadata = {assoc.folder_id: (assoc.integrity_manifest, assoc.mb_size) for assoc in self.snapshot.directories}
        original_date_last_modified = self.snapshot.date_last_modified
        try:
            for dir_assoc in self.snapshot.directories:
                system_path = Path(dir_assoc.original_path)
                snapshot_copy_path = self._snapshot_child_path(dir_assoc.directory_name)

                # 4. Copy each source to staging
                staging_dir = self._snapshot_child_path(f"{dir_assoc.directory_name}_staging_{gen_random_string(6)}")
                backup_dir = self._snapshot_child_path(f"{dir_assoc.directory_name}_bck_{gen_random_string(6)}")

                logger.info(f"Copying '{system_path}' to staging '{staging_dir}'")

                try:
                    updated_manifests[dir_assoc.folder_id] = {}
                    self.settings.copy_strategy.copy_directory(
                        system_path,
                        staging_dir,
                        message_callback=message_callback,
                        manifest=updated_manifests[dir_assoc.folder_id],
                    )
                except Exception as e:
                    if staging_dir.exists():
                        shutil.rmtree(staging_dir)
                    raise RuntimeError(f"Failed to copy system path '{system_path}' to staging '{staging_dir}': {e}") from e

                rollbacks.append(
                    {
                        "snapshot_copy_path": snapshot_copy_path,
                        "staging_dir": staging_dir,
                        "backup_dir": backup_dir,
                        "dir_assoc": dir_assoc,
                        "system_path": system_path,
                    }
                )

            # Replace internal copy only at the end
            for rb in rollbacks:
                snap_path = rb["snapshot_copy_path"]
                staging_dir = rb["staging_dir"]
                backup_dir = rb["backup_dir"]

                if snap_path.exists():
                    snap_path.rename(backup_dir)

                staging_dir.rename(snap_path)

            # Update metadata while backups are still intact.
            for rb in rollbacks:
                dir_assoc = rb["dir_assoc"]
                dir_assoc.mb_size = get_folder_size_mb(rb["system_path"])
                dir_assoc.integrity_manifest = updated_manifests[dir_assoc.folder_id]

            self.snapshot.date_last_modified = datetime.now()
            self.__save_json()

        except Exception as e:
            logger.error(f"Update from system failed during transaction. Rolling back. Reason: {e}")
            for rb in rollbacks:
                snap_path = rb["snapshot_copy_path"]
                staging_dir = rb["staging_dir"]
                backup_dir = rb["backup_dir"]

                if staging_dir.exists():
                    shutil.rmtree(staging_dir)

                if backup_dir.exists():
                    if snap_path.exists():
                        shutil.rmtree(snap_path)
                    backup_dir.rename(snap_path)
            for assoc in self.snapshot.directories:
                assoc.integrity_manifest, assoc.mb_size = original_metadata[assoc.folder_id]
            self.snapshot.date_last_modified = original_date_last_modified
            raise

        SnapshotUtils.cleanup_after_commit((rb["backup_dir"] for rb in rollbacks), "Update from system")

    def remove_installed_copies(self, message_callback=None):
        """
        Removes all directories on the system that this snapshot is managing.
        This is effectively an 'uninstall' operation for the snapshot's associated directories.
        It only removes the copies at the 'original_path' locations, not the snapshot's
        internal backup.

        Raises:
            ExceptionGroup: If any target could not be removed. Other targets
                            are still attempted, and metadata is left unchanged.
        """
        SnapshotInstaller(self._storage()).remove_installed_copies(message_callback=message_callback)

    def install(self, enable_everyone_full_control: bool = False, clear_destination: bool = True, progress_callback=None, message_callback=None):
        """
        Installs the snapshot's contents to their original locations on the filesystem.
        This will clear the destination directories before copying the snapshot's contents.

        Args:
            enable_everyone_full_control (bool): If True and on Windows, it will attempt
                to set full control permissions for the 'Everyone' group on the
                installed directories. Defaults to False; ACL changes require explicit opt-in.
            clear_destination (bool): If True, clears the destination directories before copying.
        """
        SnapshotInstaller(self._storage()).install(enable_everyone_full_control, clear_destination, progress_callback, message_callback)

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
            self.snapshot.validate()
            self._snapshot_root_path()
            snapshot_json_path = self._snapshot_child_path(self.settings.json_filename)
            if backup_type == BackupType.SNAPSHOT_DIRECTORY and not snapshot_json_path.is_file():
                raise FileNotFoundError(f"Snapshot metadata '{snapshot_json_path}' is missing.")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            backup_type_suffix = ""
            if backup_type == BackupType.ASSOCIATED_DIRECTORIES:
                backup_type_suffix = "_ad"
            elif backup_type == BackupType.SNAPSHOT_DIRECTORY:
                backup_type_suffix = "_sd"

            if is_export:
                zip_name = f"{prefix}_{self.snapshot.id}{backup_type_suffix}_{timestamp}.zip"
            else:
                zip_name = f"backup_{prefix}_{self.snapshot.id}{backup_type_suffix}_{timestamp}.zip"

            backup_path.mkdir(parents=True, exist_ok=True)
            zip_path = backup_path.joinpath(zip_name)

            def files_to_archive():
                if backup_type == BackupType.ASSOCIATED_DIRECTORIES:
                    for d in self.snapshot.directories:
                        folder = Path(d.original_path)
                        try:
                            mode = folder.stat().st_mode
                        except FileNotFoundError:
                            # A missing installation target has no data to protect.
                            continue
                        if not stat.S_ISDIR(mode):
                            raise NotADirectoryError(f"Backup source '{folder}' is not a directory.")
                        for file_path in SnapshotUtils.iter_files_strict(folder):
                            yield file_path, Path(d.directory_name) / file_path.relative_to(folder)
                else:
                    snapshot_root = self._snapshot_root_path()
                    SnapshotUtils.assert_no_symlinks(snapshot_root)
                    for file_path in SnapshotUtils.iter_files_strict(snapshot_root):
                        yield file_path, file_path.relative_to(self.path_snapshot)

            return SnapshotUtils.write_verified_zip(zip_path, files_to_archive(), message_callback)
        except Exception as e:
            logger.error(f"Failed to create backup for snapshot '{self.snapshot.id}': {e}")
            raise

    def _storage(self) -> SnapshotStorage:
        """Build operation dependencies from the facade's current public state."""
        return SnapshotStorage(self.snapshot, self.settings, self.path_catalogue, self.path_snapshot, self.path_snapshot_json)
