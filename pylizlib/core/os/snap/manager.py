"""Public facade for one snapshot lifecycle and its mutable storage context.

Filesystem workflows live in operations; this module retains public methods,
legacy metadata-update ordering and the small association add/remove API."""

from datetime import datetime
from pathlib import Path

from pylizlib.core.data.gen import gen_random_string
from pylizlib.core.os.path import remove_directory_or_move_to_temp
from pylizlib.core.os.snap.domain import (
    BackupType,
    SnapDirAssociation,
    SnapEditAction,
    Snapshot,
    SnapshotSettings,
    validate_directory_component,
)
from pylizlib.core.os.snap.operations.archives import SnapshotArchiveService
from pylizlib.core.os.snap.operations.edits import SnapshotEditor
from pylizlib.core.os.snap.operations.install import SnapshotInstaller
from pylizlib.core.os.snap.operations.lifecycle import SnapshotLifecycle
from pylizlib.core.os.snap.operations.sync import SnapshotSynchronizer
from pylizlib.core.os.snap.serializer import SnapshotSerializer
from pylizlib.core.os.snap.storage.context import SnapshotStorage
from pylizlib.core.os.snap.storage.transactions import recover_storage_transactions
from pylizlib.core.os.snap.utils import SnapshotUtils


class SnapshotManager:
    """Public single-snapshot facade composing independently testable operations.

    The facade retains legacy signatures, shared default settings, public paths
    and return values. Each invocation builds dependencies from current state.

    Attributes:
        snapshot (Snapshot): Snapshot model used or mutated by this operation; association identities are retained
            where documented.
        settings (SnapshotSettings): Mutable snapshot settings retained by reference; no defensive copy is made.
        path_catalogue (Path): Catalogue root retained by this collaborator.
        path_snapshot (Path): Snapshot root captured by the manager/storage context.
        path_snapshot_json (Path): Metadata file path captured when the manager/storage context was constructed.
    """

    def __init__(
        self,
        snapshot: Snapshot,
        catalogue_path: Path,
        settings: SnapshotSettings = SnapshotSettings(),
    ):
        """Initializes a manager for a single snapshot's lifecycle.

        Args:
            snapshot (Snapshot): The `Snapshot` object to manage.
            catalogue_path (Path): The root path of the snapshot catalogue.
            settings (SnapshotSettings): Configuration settings for the manager.

        Returns:
            None: No return value.

        Notes:
            Omitting settings reuses this constructor's mutable default SnapshotSettings object. Pass a new settings
            object for independent configuration. Stored paths are captured once; later changes to snapshot.id or
            json_filename are rejected by storage checks.
        """
        self.snapshot = snapshot
        self.settings = settings
        self.path_catalogue = catalogue_path
        self.snapshot.validate()
        validate_directory_component(self.settings.json_filename, "Snapshot JSON filename")
        self.path_snapshot = SnapshotUtils.validate_snapshot_root(self.snapshot.folder_name, self.path_catalogue)
        self.path_snapshot_json = SnapshotUtils.get_snapshot_json_path(self.snapshot.folder_name, self.path_catalogue, self.settings.json_filename)

    def _snapshot_root_path(self) -> Path:
        """Validate that the catalogue entry still names this snapshot root.

        Returns:
            Path: Revalidated root matching the snapshot ID captured when the manager was created.
        """
        return self._storage().root_path()

    def _snapshot_child_path(self, name: str) -> Path:
        """Return a validated, contained child of this snapshot.

        Args:
            name (str): Attribute or filesystem-entry name inspected by this operation.

        Returns:
            Path: Validated direct child below the captured stored snapshot root.
        """
        return self._storage().child_path(name)

    def __save_json(self):
        """Saves the current snapshot object state to its JSON file.

        Returns:
            None: No return value.
        """
        self._storage().save_json()

    def create(self, progress_callback=None, message_callback=None, *, replace_existing: bool = False):
        """Creates the snapshot by preparing its contents and metadata in staging.

        Existing IDs are rejected unless replace_existing=True. An explicit
        replacement retains the old directory until publication succeeds and
        restores it if publication fails. Cleanup runs after commit.

        Args:
            progress_callback (SnapshotPercentCallback | None): Optional observer receiving integer aggregate
                percentage from 0 through 100; return values do not cancel the operation.
            message_callback (MessageCallback | None): Optional status observer receiving one message string; its
                exceptions propagate according to the calling operation.
            replace_existing (bool): Allow an existing snapshot ID to be replaced when True; otherwise collisions are
                rejected.

        Returns:
            None: No return value.

        Raises:
            FileExistsError: If the destination exists and replacement is disabled.
        """
        SnapshotLifecycle(self._storage()).create(progress_callback, message_callback, replace_existing=replace_existing)

    def delete(self, message_callback=None):
        """Deletes the snapshot's directory, propagating filesystem failures.

        Args:
            message_callback (MessageCallback | None): Optional status observer receiving one message string; its
                exceptions propagate according to the calling operation.

        Returns:
            None: No return value.
        """
        SnapshotLifecycle(self._storage()).delete(message_callback=message_callback)

    def update_json_data_fields(self):
        """Updates the 'data' and 'date_last_modified' fields in the snapshot's JSON file.
        This method is typically called after modifying the snapshot's data dictionary.

        Returns:
            None: No return value.
        """
        recover_storage_transactions(self._storage())
        self.snapshot.validate()
        json_path = self._snapshot_child_path(self.settings.json_filename)
        SnapshotSerializer.update_field(json_path, "data", self.snapshot.data)
        SnapshotSerializer.update_field(json_path, "date_last_modified", datetime.now().isoformat())
        self.snapshot.date_last_modified = datetime.now()

    def update_json_base_fields(self):
        """Updates the basic metadata fields (name, desc, author, tags, date_modified)
        of the snapshot's JSON file.

        Returns:
            None: No return value.
        """
        recover_storage_transactions(self._storage())
        self.snapshot.validate()
        json_path = self._snapshot_child_path(self.settings.json_filename)
        SnapshotSerializer.update_field(json_path, "name", self.snapshot.name)
        SnapshotSerializer.update_field(json_path, "desc", self.snapshot.desc)
        SnapshotSerializer.update_field(json_path, "author", self.snapshot.author)
        SnapshotSerializer.update_field(json_path, "tags", self.snapshot.tags)
        SnapshotSerializer.update_field(json_path, "date_modified", datetime.now().isoformat())
        self.snapshot.date_modified = datetime.now()

    def install_directory(self, destination_path: Path):
        """Adds a new directory to the snapshot, copying its contents into the
        snapshot's storage directory.

        Args:
            destination_path (Path): The path of the directory to add to the snapshot.

        Returns:
            None: No return value.

        Raises:
            ValueError: If the destination_path is not a valid directory.

        Notes:
            This legacy single-association flow copies, appends the live association and saves metadata. It does not
            use the complete edit journal; failures can have different rollback effects from update_from_actions_list.
        """
        recover_storage_transactions(self._storage())
        if not destination_path.exists() or not destination_path.is_dir():
            raise ValueError(f"The provided path {destination_path} is not a valid directory.")
        used_ids = {association.folder_id for association in self.snapshot.directories}
        existing_indices = [association.index for association in self.snapshot.directories]
        index = max(existing_indices, default=0) + 1
        storage_root = self._snapshot_root_path()
        while True:
            folder_id = gen_random_string(self.settings.folder_id_length)
            if folder_id in used_ids:
                continue
            new_dir = SnapDirAssociation(index=index, original_path=destination_path.as_posix(), folder_id=folder_id)
            stored_path = storage_root / new_dir.directory_name
            if not stored_path.exists() and not stored_path.is_symlink():
                break
            used_ids.add(folder_id)
        manifest = {}
        new_dir.copy_install_to(
            storage_root,
            copy_strategy=self.settings.copy_strategy,
            manifest=manifest,
        )
        self.snapshot.directories.append(new_dir)
        self.__save_json()

    def uninstall_directory_by_folder_id(self, folder_id: str):
        """Removes a directory from the snapshot based on its folder_id.
        This deletes the directory's copy from the snapshot's storage and updates the JSON file.

        Args:
            folder_id (str): The unique ID of the folder to remove.

        Returns:
            None: No return value.
        """
        recover_storage_transactions(self._storage())
        dir_to_remove = next((d for d in self.snapshot.directories if d.folder_id == folder_id), None)
        if dir_to_remove:
            dir_path = self._snapshot_child_path(dir_to_remove.directory_name)
            remove_directory_or_move_to_temp(dir_path)
            self.snapshot.directories.remove(dir_to_remove)
            self.__save_json()

    def update_from_actions_list(self, edits: list[SnapEditAction], message_callback=None):
        """Plans edits by association ID against the stored metadata, then stages all
        affected copies before assigning final names. Originals remain available
        for rollback until the updated metadata has been saved.

        Args:
            edits (list[SnapEditAction]): A list of SnapEditAction objects.
            message_callback (MessageCallback | None): Optional status observer receiving one message string; its
                exceptions propagate according to the calling operation.

        Returns:
            None: No return value.
        """
        SnapshotEditor(self._storage()).apply(edits, message_callback=message_callback)

    def duplicate(self, message_callback=None):
        """Creates a duplicate of the current snapshot with a new ID and name.
        The entire snapshot directory is copied, and a new JSON file is created for the copy.

        Args:
            message_callback (MessageCallback | None): Optional status observer receiving one message string; its
                exceptions propagate according to the calling operation.

        Returns:
            None: No return value.

        Raises:
            FileNotFoundError: If the original snapshot path does not exist.
        """
        SnapshotLifecycle(self._storage()).duplicate(message_callback=message_callback)

    def update_associated_dirs_from_system(self, message_callback=None):
        """Updates the snapshot's internal copy of each associated directory
        with the current version from the original system path.

        Args:
            message_callback (MessageCallback | None): Optional status observer receiving one message string; its
                exceptions propagate according to the calling operation.

        Returns:
            None: No return value.
        """
        SnapshotSynchronizer(self._storage()).update_associated_dirs_from_system(message_callback=message_callback)

    def remove_installed_copies(self, message_callback=None):
        """Removes all directories on the system that this snapshot is managing.
        This is effectively an 'uninstall' operation for the snapshot's associated directories.
        It only removes the copies at the 'original_path' locations, not the snapshot's
        internal backup.

        Args:
            message_callback (MessageCallback | None): Optional status observer receiving one message string; its
                exceptions propagate according to the calling operation.

        Returns:
            None: No return value.

        Raises:
            ExceptionGroup: If any target could not be removed. Other targets are still attempted, and metadata is
                left unchanged.
        """
        SnapshotInstaller(self._storage()).remove_installed_copies(message_callback=message_callback)

    def install(self, enable_everyone_full_control: bool = False, clear_destination: bool = True, progress_callback=None, message_callback=None):
        """Installs the snapshot's contents to their original locations on the filesystem.
        Copies are prepared and verified in staging before live destinations are replaced or merged.

        Args:
            enable_everyone_full_control (bool): If True and on Windows, it will attempt to set full control
                permissions for the 'Everyone' group on the installed directories. Defaults to False; ACL changes
                require explicit opt-in.
            clear_destination (bool): Replace entire live roots after all staging copies complete when True; False
                merges by replacing colliding top-level children and retaining unrelated ones.
            progress_callback (SnapshotPercentCallback | None): Optional observer receiving integer aggregate
                percentage from 0 through 100; return values do not cancel the operation.
            message_callback (MessageCallback | None): Optional status observer receiving one message string; its
                exceptions propagate according to the calling operation.

        Returns:
            None: No return value.

        Raises:
            ValueError: If two associated install paths are the same or nested.
            SnapshotInstallMetadataError: The directory contents were installed, but updating ``date_last_used``
                failed. Inspect ``metadata_published`` to determine whether the JSON update became visible.

        Notes:
            Every association is staged before live publication. clear_destination=False performs top-level
            replacement/merge, retaining unrelated live children. SnapshotInstallMetadataError means contents are
            installed even though date_last_used or final journal persistence failed; inspect metadata_published and
            durability_confirmed before retrying.
        """
        SnapshotInstaller(self._storage()).install(enable_everyone_full_control, clear_destination, progress_callback, message_callback)

    def create_backup(self, backup_path: Path, prefix: str, backup_type: "BackupType", is_export: bool = False, message_callback=None) -> Path:
        """Creates, verifies and atomically publishes a zip archive of the snapshot's data.
        Failures propagate to the caller so protected operations cannot continue.

        Args:
            backup_path (Path): The directory where the backup zip file will be saved.
            prefix (str): A prefix for the backup filename.
            backup_type (BackupType): The type of backup to create (associated directories or the snapshot directory).
            is_export (bool): If True, the filename will be formatted as an export.
            message_callback (MessageCallback | None): Optional status observer receiving one message string; its
                exceptions propagate according to the calling operation.

        Returns:
            Path: The path of the verified, published archive.

        Raises:
            SnapshotIncompleteError: If an associated-directory backup is missing one or more source folders. Inspect
                ``missing_folders``.
        """
        return SnapshotArchiveService(self._storage()).create_backup(backup_path, prefix, backup_type, is_export, message_callback)

    def _storage(self) -> SnapshotStorage:
        """Build operation dependencies from the facade's current public state.

        Returns:
            SnapshotStorage: Operation context using current live model/settings and the originally captured manager
                paths.
        """
        return SnapshotStorage(self.snapshot, self.settings, self.path_catalogue, self.path_snapshot, self.path_snapshot_json)
