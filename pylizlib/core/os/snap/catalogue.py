"""Public catalogue API composing lookup, backup, transfer and snapshot services.

This facade owns backup triggers and caller-visible orchestration. Storage
scans and archive algorithms live in dedicated internal modules."""

from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Optional

from pylizlib.core.log.pylizLogger import logger
from pylizlib.core.os.snap.domain import (
    BackupType,
    SnapEditAction,
    Snapshot,
    SnapshotBackupInfo,
    SnapshotSettings,
    validate_directory_component,
)
from pylizlib.core.os.snap.manager import SnapshotManager
from pylizlib.core.os.snap.operations.archives import CatalogueBackupService
from pylizlib.core.os.snap.operations.backup_names import parse_backup_filename
from pylizlib.core.os.snap.operations.transfers import CatalogueTransferService
from pylizlib.core.os.snap.storage.catalogue import _is_operational_directory, read_catalogue, read_snapshot_by_id
from pylizlib.core.os.snap.storage.coordination import catalogue_access
from pylizlib.core.os.snap.storage.transactions import recover_pending_transactions, recover_storage_transactions
from pylizlib.core.os.snap.utils import SnapshotUtils


class SnapshotCatalogue:
    """Public catalogue facade coordinating lookup, backup policy and operations.

    Paths and mutable settings are read for each invocation. Backup, transfer
    and single-snapshot services own their respective filesystem workflows.

    Operations share an exclusive catalogue gate with other threads/processes.
    Contention raises SnapshotBusyError immediately. Metadata queries inside
    progress/message observers skip active journals; observer mutations fail
    before modifying data. The persistent lock sidecar must remain in place.

    Attributes:
        path_catalogue (Path): Catalogue root retained by this collaborator.
        settings (SnapshotSettings): Mutable snapshot settings retained by reference; no defensive copy is made.
    """

    def __init__(self, path_catalogue: Path, settings: SnapshotSettings = SnapshotSettings()):
        """Initializes the catalogue manager for a collection of snapshots.

        Args:
            path_catalogue (Path): The root directory path for the catalogue.
            settings (SnapshotSettings): Global settings to apply to snapshots in this catalogue.

        Returns:
            None: No return value.

        Notes:
            Omitting settings reuses this constructor's mutable default settings object. Managers created by this
            catalogue retain the same settings reference.
        """
        self.path_catalogue = path_catalogue
        self.settings = settings
        validate_directory_component(self.settings.json_filename, "Snapshot JSON filename")
        self.path_catalogue.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _parse_backup_info(backup_path: Path) -> SnapshotBackupInfo:
        """Parse legacy filename hints when no embedded backup manifest is available.

        Args:
            backup_path (Path): Archive file path whose basename supplies legacy naming hints; this argument is not an
                output directory.

        Returns:
            SnapshotBackupInfo: Legacy filename hints; unknown identity/type/timestamp remain unset when not
                recognizable.
        """
        return parse_backup_filename(backup_path)

    def list_backups(self, backup_dir: Path) -> list[SnapshotBackupInfo]:
        """List every file recognized as a ZIP archive, regardless of its filename suffix.

        Args:
            backup_dir (Path): Folder containing backup archives.

        Returns:
            list[SnapshotBackupInfo]: A list of parsed backup metadata entries sorted by date (newest first).

        Raises:
            SnapshotBusyError: Another operation owns the catalogue, or an observer attempts a modifying call.
        """
        with catalogue_access(self.path_catalogue, write=False):
            return self._backups().list_backups(backup_dir)

    def restore_backup(self, backup_zip_path: Path):
        """Restores a backup using embedded archive metadata, with filename fallback
        for legacy ZIPs. Renaming a new backup does not change its interpretation.

        Args:
            backup_zip_path (Path): Path of the backup .zip archive.

        Returns:
            None: No return value.

        Raises:
            SnapshotBusyError: Another operation owns the catalogue, or an observer attempts a modifying call.
            ValueError: If the archive path is invalid, embedded metadata is not supported, or the restore cannot be
                performed.
            SnapshotIncompleteError: If an associated-directories backup is missing expected folders. Inspect
                ``missing_folders`` and ``unexpected_entries``.
            IOError: If extraction fails.
        """
        with catalogue_access(self.path_catalogue):
            self._backups().restore_backup(backup_zip_path)

    def restore_backup_with_mapping(self, backup_zip_path: Path, destination_mapping: Mapping[str, str | Path]) -> None:
        """Restore an AD backup with explicit destination overrides.

        Keys are persistent association ``folder_id`` values from the archive
        manifest. Paths not included in the mapping use their captured origin.
        This supports restoring a backup after its snapshot has been removed or
        when the original folders have moved.

        Args:
            backup_zip_path (Path): Backup archive path; embedded metadata takes precedence over legacy filename
                hints.
            destination_mapping (Mapping[str, str | Path]): Overrides keyed by stable folder_id; unmapped AD
                associations retain their archived source paths.

        Returns:
            None: No return value.

        Raises:
            SnapshotBusyError: Another operation owns the catalogue, or an observer attempts a modifying call.

        Notes:
            Only AD archives accept mapping, including an empty mapping. Mapping does not bypass OS or destructive-
            path checks. Standalone restore requires embedded associations and origin OS; older archives missing
            either still need catalogue metadata.
        """
        with catalogue_access(self.path_catalogue):
            self._backups().restore_backup_with_mapping(backup_zip_path, destination_mapping)

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
        with catalogue_access(self.path_catalogue):
            self._backups().delete_backup(backup_zip_path)

    def set_catalogue_path(self, new_path: Path):
        """Sets a new path for the snapshot catalogue.
        The directory will be created if it does not exist.

        Args:
            new_path (Path): The new path for the catalogue.

        Returns:
            None: No return value.

        Raises:
            SnapshotBusyError: Another operation owns the catalogue, or an observer attempts a modifying call.
        """
        with catalogue_access(self.path_catalogue):
            self.path_catalogue = new_path
            self.path_catalogue.mkdir(parents=True, exist_ok=True)

    def add(self, snap: Snapshot, progress_callback=None, message_callback=None):
        """Adds a new snapshot to the catalogue.

        Args:
            snap (Snapshot): Snapshot model identifying the stored tree or operation target.
            progress_callback (SnapshotPercentCallback | None): Optional observer receiving integer aggregate
                percentage from 0 through 100; return values do not cancel the operation.
            message_callback (MessageCallback | None): Optional status observer receiving one message string; its
                exceptions propagate according to the calling operation.

        Returns:
            None: No return value.

        Raises:
            SnapshotBusyError: Another operation owns the catalogue, or an observer attempts a modifying call.
            FileExistsError: If the snapshot's ID is already present.
        """
        with catalogue_access(self.path_catalogue):
            snap_manager = self._manager(snap)
            snap_manager.create(progress_callback=progress_callback, message_callback=message_callback)

    def delete(self, snap: Snapshot, message_callback=None):
        """Deletes a snapshot from the catalogue.

        If backup settings are enabled, a backup is created before deletion.

        Args:
            snap (Snapshot): The Snapshot object to delete.
            message_callback (MessageCallback | None): Optional status observer receiving one message string; its
                exceptions propagate according to the calling operation.

        Returns:
            None: No return value.

        Raises:
            SnapshotBusyError: Another operation owns the catalogue, or an observer attempts a modifying call.
        """
        with catalogue_access(self.path_catalogue):
            snap_manager = self._manager(snap)
            if self.settings.bck_before_delete_enabled:
                snap_manager.create_backup(self.settings.backup_path, "beforeDelete", BackupType.SNAPSHOT_DIRECTORY)
            snap_manager.delete(message_callback=message_callback)

    def get_all(self, *, strict: bool = False) -> list[Snapshot]:
        """Retrieves all snapshots from the catalogue.

        Args:
            strict (bool): Propagate filesystem errors instead of skipping unreadable entries.

        Returns:
            list[Snapshot]: A list of Snapshot objects found in the catalogue.

        Raises:
            SnapshotBusyError: Another operation owns the catalogue, or an observer attempts a modifying call.

        Notes:
            Recovery runs before scanning and may rename/delete transaction paths or complete metadata writes.
            strict=True propagates filesystem errors; malformed or domain-invalid metadata is still logged and
            skipped. Operational directories are excluded. When called by an active operation's observer,
            recovery skips that operation's journals and reads the currently published metadata.
        """
        with catalogue_access(self.path_catalogue, write=False):
            recover_pending_transactions(self.path_catalogue)
            snapshots = read_catalogue(self.path_catalogue, self.settings, strict=strict)
            for snapshot in snapshots:
                recover_storage_transactions(self._manager(snapshot)._storage())
            return snapshots

    def get_by_id(self, snap_id: str) -> Optional[Snapshot]:
        """Retrieves a single snapshot from the catalogue by its ID.

        Args:
            snap_id (str): The ID of the snapshot to retrieve.

        Returns:
            Optional[Snapshot]: The Snapshot object if found, otherwise None.

        Raises:
            SnapshotBusyError: Another operation owns the catalogue, or an observer attempts a modifying call.

        Notes:
            Recovery runs before direct O(1)-style lookup and may modify stored data or raise. The subsequent per-
            entry metadata lookup logs malformed/unreadable entries and returns None. Observer reentry skips
            the current operation's journals instead of treating them as abandoned work.
        """
        with catalogue_access(self.path_catalogue, write=False):
            recover_pending_transactions(self.path_catalogue)
            snapshot = read_snapshot_by_id(self.path_catalogue, snap_id, self.settings)
            if snapshot is not None:
                recover_storage_transactions(self._manager(snapshot)._storage())
            return snapshot

    def update_snapshot_by_objs(self, old: Snapshot, new: Snapshot, message_callback=None):
        """Updates a snapshot by comparing the old and new Snapshot objects.
        It calculates the differences and applies them.

        Args:
            old (Snapshot): The original Snapshot object.
            new (Snapshot): The new Snapshot object with the desired changes.
            message_callback (MessageCallback | None): Optional status observer receiving one message string; its
                exceptions propagate according to the calling operation.

        Returns:
            None: No return value.

        Raises:
            SnapshotBusyError: Another operation owns the catalogue, or an observer attempts a modifying call.
        """
        with catalogue_access(self.path_catalogue):
            edits = SnapshotUtils.get_edits_between_snapshots(old, new)
            self.update_snapshot_by_edits(new, edits, message_callback=message_callback)

    def update_snapshot_by_edits(self, snap: Snapshot, edits: list[SnapEditAction], message_callback=None):
        """Updates a snapshot using a pre-computed list of edit actions.

        If backup settings are enabled, a backup is created before the update.

        Args:
            snap (Snapshot): The Snapshot object to update.
            edits (list[SnapEditAction]): A list of SnapEditAction objects to apply.
            message_callback (MessageCallback | None): Optional status observer receiving one message string; its
                exceptions propagate according to the calling operation.

        Returns:
            None: No return value.

        Raises:
            SnapshotBusyError: Another operation owns the catalogue, or an observer attempts a modifying call.
        """
        with catalogue_access(self.path_catalogue):
            snap_manager = self._manager(snap)
            if self.settings.bck_before_modify_enabled:
                snap_manager.create_backup(self.settings.backup_path, "beforeEdit", BackupType.SNAPSHOT_DIRECTORY)
            snap_manager.snapshot.date_modified = datetime.now()
            snap_manager.snapshot.date_last_modified = datetime.now()
            snap_manager.update_from_actions_list(edits, message_callback=message_callback)

    def duplicate_by_id(self, snap_id: str, message_callback=None):
        """Duplicates a snapshot by its ID.

        Args:
            snap_id (str): The ID of the snapshot to duplicate.
            message_callback (MessageCallback | None): Optional status observer receiving one message string; its
                exceptions propagate according to the calling operation.

        Returns:
            None: No return value.

        Raises:
            SnapshotBusyError: Another operation owns the catalogue, or an observer attempts a modifying call.
            ValueError: If no snapshot is found with the given ID.
        """
        with catalogue_access(self.path_catalogue):
            snap = self.get_by_id(snap_id)
            if snap is None:
                raise ValueError(f"No snapshot found with ID {snap_id}")
            snap_manager = self._manager(snap)
            snap_manager.duplicate(message_callback=message_callback)

    def export_assoc_dirs(self, snap_id: str, destination_path: Path, message_callback=None):
        """Exports the associated directories of a snapshot to a zip file.

        Args:
            snap_id (str): The ID of the snapshot to export.
            destination_path (Path): The folder where the exported zip file will be saved.
            message_callback (MessageCallback | None): Optional status observer receiving one message string; its
                exceptions propagate according to the calling operation.

        Returns:
            None: No return value.

        Raises:
            SnapshotBusyError: Another operation owns the catalogue, or an observer attempts a modifying call.
            SnapshotIncompleteError: If any associated source folder is missing. Inspect ``missing_folders``.
        """
        with catalogue_access(self.path_catalogue):
            snap = self._require_snapshot(snap_id)

            snap_manager = self._manager(snap)

            # Use the existing create_backup method with a specific prefix for export
            snap_manager.create_backup(destination_path, "export", BackupType.ASSOCIATED_DIRECTORIES, is_export=True, message_callback=message_callback)

    def export_snapshot(self, snap_id: str, destination_path: Path, message_callback=None):
        """Exports the entire snapshot directory (the internal backup) to a zip file.

        Args:
            snap_id (str): The ID of the snapshot to export.
            destination_path (Path): The folder where the exported zip file will be saved.
            message_callback (MessageCallback | None): Optional status observer receiving one message string; its
                exceptions propagate according to the calling operation.

        Returns:
            None: No return value.

        Raises:
            SnapshotBusyError: Another operation owns the catalogue, or an observer attempts a modifying call.
        """
        with catalogue_access(self.path_catalogue):
            snap = self._require_snapshot(snap_id)

            snap_manager = self._manager(snap)
            snap_manager.create_backup(destination_path, "export_snap", BackupType.SNAPSHOT_DIRECTORY, is_export=True, message_callback=message_callback)

    def export_catalogue(self, destination_path: Path, file_name: str = "catalogue_export.zip"):
        """Exports the entire catalogue to a single zip file.

        Args:
            destination_path (Path): The folder where the exported zip file will be saved.
            file_name (str): The name for the output zip file.

        Returns:
            Path | None: Published ZIP path, or None when the catalogue has no snapshots.

        Raises:
            SnapshotBusyError: Another operation owns the catalogue, or an observer attempts a modifying call.
        """
        with catalogue_access(self.path_catalogue):
            return self._transfers().export_catalogue(destination_path, file_name)

    def import_catalogue(self, zip_path: Path):
        """Imports all snapshots from a catalogue zip file, skipping existing ones.

        Args:
            zip_path (Path): The path to the catalogue .zip file.

        Returns:
            None: No return value.

        Raises:
            SnapshotBusyError: Another operation owns the catalogue, or an observer attempts a modifying call.
            ValueError: If the provided path is not a valid .zip file.
            IOError: If the zip file fails to extract.
        """
        with catalogue_access(self.path_catalogue):
            self._transfers().import_catalogue(zip_path)

    def import_snapshot(self, zip_path: Path):
        """Imports a snapshot from a zip file into the catalogue.

        Args:
            zip_path (Path): The path to the .zip file to import.

        Returns:
            None: No return value.

        Raises:
            SnapshotBusyError: Another operation owns the catalogue, or an observer attempts a modifying call.
            ValueError: If the path is not a valid zip file, if the zip is corrupted, if the snapshot.json is missing,
                or if a snapshot with the same ID already exists.
            IOError: If the zip file fails to extract.
        """
        with catalogue_access(self.path_catalogue):
            self._transfers().import_snapshot(zip_path)

    def update_assoc_with_installed(self, snap_id: str, message_callback=None):
        """Updates the snapshot's internal copy of associated directories
        with the current state of those directories on the filesystem.

        Args:
            snap_id (str): Snapshot ID identifying the catalogue entry, rather than its display name.
            message_callback (MessageCallback | None): Optional status observer receiving one message string; its
                exceptions propagate according to the calling operation.

        Returns:
            None: No return value.

        Raises:
            SnapshotBusyError: Another operation owns the catalogue, or an observer attempts a modifying call.
        """
        with catalogue_access(self.path_catalogue):
            snap = self._require_snapshot(snap_id)

            snap_manager = self._manager(snap)
            if self.settings.bck_before_modify_enabled:
                snap_manager.create_backup(self.settings.backup_path, "beforeUpdateLocal", BackupType.SNAPSHOT_DIRECTORY)
            snap_manager.update_associated_dirs_from_system(message_callback=message_callback)

    def remove_installed_copies(self, snap_id: str, message_callback=None):
        """Removes the installed copies of a snapshot's associated directories from the system.

        Args:
            snap_id (str): The ID of the snapshot whose installed copies should be removed.
            message_callback (MessageCallback | None): Optional status observer receiving one message string; its
                exceptions propagate according to the calling operation.

        Returns:
            None: No return value.

        Raises:
            SnapshotBusyError: Another operation owns the catalogue, or an observer attempts a modifying call.
        """
        with catalogue_access(self.path_catalogue):
            snap = self.get_by_id(snap_id)
            if not snap:
                logger.warning(f"Snapshot with ID '{snap_id}' not found. Cannot remove installed copies.")
                return
            snap_manager = self._manager(snap)
            snap_manager.remove_installed_copies(message_callback=message_callback)

    def install(self, snap: Snapshot, clear_destination: bool = True, progress_callback=None, message_callback=None):
        """Installs a snapshot's contents to their original target locations.

        If backup settings are enabled, a backup of the target locations is created first.

        Args:
            snap (Snapshot): The Snapshot object to install.
            clear_destination (bool): Replace entire live roots after all staging copies complete when True; False
                merges by replacing colliding top-level children and retaining unrelated ones.
            progress_callback (SnapshotPercentCallback | None): Optional observer receiving integer aggregate
                percentage from 0 through 100; return values do not cancel the operation.
            message_callback (MessageCallback | None): Optional status observer receiving one message string; its
                exceptions propagate according to the calling operation.

        Returns:
            None: No return value.

        Raises:
            SnapshotBusyError: Another operation owns the catalogue, or an observer attempts a modifying call.
            ValueError: A value, path, resource limit or metadata field violates the validation rules described above.

        Notes:
            The selected snapshot is resolved through recovery-aware lookup, then installed using the current shared
            settings. Every copy is staged first. clear_destination=False retains unrelated top-level children. A
            post-commit SnapshotInstallMetadataError reports installed contents with incomplete metadata confirmation.
        """
        with catalogue_access(self.path_catalogue):
            stored_snapshot = self.get_by_id(snap.id)
            if stored_snapshot is None:
                raise ValueError(f"No snapshot found with ID {snap.id}.")

            # The caller may hold a model loaded before the snapshot was updated.
            # Installation must use the persisted manifest that matches on-disk data.
            snap_manager = self._manager(stored_snapshot)
            if self.settings.bck_before_install_enabled:
                snap_manager.create_backup(
                    self.settings.backup_path,
                    "preinstall",
                    BackupType.ASSOCIATED_DIRECTORIES,
                )
            snap_manager.install(self.settings.install_with_everyone_full_control, clear_destination=clear_destination, progress_callback=progress_callback, message_callback=message_callback)
            snap.date_last_used = stored_snapshot.date_last_used

    def exists(self, snap_id: str) -> bool:
        """Checks if a snapshot with the given ID exists in the catalogue.

        Args:
            snap_id (str): The ID of the snapshot to check.

        Returns:
            bool: True if the snapshot exists, False otherwise.

        Raises:
            SnapshotBusyError: Another operation owns the catalogue, or an observer attempts a modifying call.

        Notes:
            This is a metadata-based lookup, not a pure path-existence predicate. Recovery runs first and may perform
            writes or raise; an existing but invalid directory does not count as a snapshot.
        """
        with catalogue_access(self.path_catalogue, write=False):
            return self.get_by_id(snap_id) is not None

    def get_snap_directory_path(self, snap: Snapshot) -> Path | None:
        """Gets the filesystem path to a snapshot's storage directory.

        Args:
            snap (Snapshot): The Snapshot object.

        Returns:
            Path | None: The Path to the snapshot's directory, or None if the snapshot doesn't exist. The supplied
                snapshot is treated as already loaded. The method checks its contained directory and metadata entry
                without decoding the JSON again.

        Raises:
            SnapshotBusyError: Another operation owns the catalogue, or an observer attempts a modifying call.
        """
        with catalogue_access(self.path_catalogue, write=False):
            if _is_operational_directory(snap.id):
                return None
            try:
                snapshot_path = SnapshotUtils.validate_snapshot_root(snap.folder_name, self.path_catalogue)
                snapshot_json_path = SnapshotUtils.get_snapshot_json_path(snap.folder_name, self.path_catalogue, self.settings.json_filename)
            except ValueError:
                return None
            if not snapshot_path.is_dir() or not snapshot_json_path.is_file():
                return None
            return snapshot_path

    def _backups(self) -> CatalogueBackupService:
        """Build backup dependencies from the current path, settings and lookup.

        Returns:
            CatalogueBackupService: Backup facade bound to current catalogue path, shared settings and parser/lookup
                hooks.
        """
        return CatalogueBackupService(self.path_catalogue, self.settings, self, self._parse_backup_info)

    def _transfers(self) -> CatalogueTransferService:
        """Build transfer dependencies from the current catalogue path/settings.

        Returns:
            CatalogueTransferService: Transfer coordinator bound to current catalogue path, shared settings and query
                methods.
        """
        return CatalogueTransferService(self.path_catalogue, self.settings, self)

    def _manager(self, snapshot: Snapshot) -> SnapshotManager:
        """Construct a manager using current shared settings without copying them.

        Args:
            snapshot (Snapshot): Snapshot model used or mutated by this operation; association identities are retained
                where documented.

        Returns:
            SnapshotManager: SnapshotManager retaining this same settings object rather than copying it.
        """
        return SnapshotManager(snapshot, self.path_catalogue, self.settings)

    def _require_snapshot(self, snap_id: str) -> Snapshot:
        """Resolve an ID for operations whose existing contract rejects absence.

        Args:
            snap_id (str): Snapshot ID identifying the catalogue entry, rather than its display name.

        Returns:
            Snapshot: Existing validated snapshot; absence raises ValueError under the operation facade contract.

        Raises:
            ValueError: A value, path, resource limit or metadata field violates the validation rules described above.
        """
        snapshot = self.get_by_id(snap_id)
        if not snapshot:
            raise ValueError(f"No snapshot found with ID {snap_id}")
        return snapshot
