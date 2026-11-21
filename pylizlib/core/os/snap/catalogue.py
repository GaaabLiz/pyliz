"""Public catalogue API composing lookup, backup, transfer and snapshot services.

This facade owns backup triggers and caller-visible orchestration. Storage
scans and archive algorithms live in dedicated internal modules."""

from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Optional

from pylizlib.core.log.pylizLogger import logger
from pylizlib.core.os.snap.callbacks import MessageCallback, SnapshotPercentCallback
from pylizlib.core.os.snap.domain import (
    BackupType,
    SnapEditAction,
    Snapshot,
    SnapshotBackupInfo,
    SnapshotCatalogueStatistics,
    SnapshotOperationResult,
    SnapshotSettings,
    SnapshotUpdateResult,
    validate_directory_component,
)
from pylizlib.core.os.snap.manager import SnapshotManager
from pylizlib.core.os.snap.operations.archives import CatalogueBackupService
from pylizlib.core.os.snap.operations.backup_names import parse_backup_filename
from pylizlib.core.os.snap.operations.configuration import build_associations, configure_snapshot
from pylizlib.core.os.snap.operations.statistics import collect_catalogue_statistics
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

    def get_backup_count(self) -> int:
        """Count ZIP archives recognized by the backup listing without inspecting archive members.

        Returns:
            int: Archive count in the configured backup directory, or zero when it is unset or missing.

        Raises:
            SnapshotBusyError: Another operation owns the catalogue.
            OSError: The configured backup directory cannot be enumerated.
        """
        with catalogue_access(self.path_catalogue, write=False):
            return self._backups().count_backups()

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

    def create_snapshot(
        self,
        *,
        snap_id: str,
        name: str,
        directory_paths: Sequence[str | Path],
        desc: str = "",
        author: str = "UnknownUser",
        tags: list[str] | None = None,
        data: Mapping[str, str] | None = None,
        progress_callback: SnapshotPercentCallback | None = None,
        message_callback: MessageCallback | None = None,
    ) -> Snapshot:
        """Capture and save a snapshot from metadata and an ordered list of source paths.

        Args:
            snap_id (str): Caller-supplied catalogue ID.
            name (str): Display name.
            directory_paths (Sequence[str | Path]): Source directories in order, with one entry per filesystem identity.
            desc (str): Display description.
            author (str): Snapshot author.
            tags (list[str] | None): Initial tags, empty when omitted.
            data (Mapping[str, str] | None): Initial custom metadata.
            progress_callback (SnapshotPercentCallback | None): Observer receiving copy progress as a percentage.
            message_callback (MessageCallback | None): Observer receiving one status message at a time.

        Returns:
            Snapshot: Saved snapshot with capture metadata and newly generated association IDs.

        Raises:
            SnapshotBusyError: Another operation owns the catalogue, or an observer attempts a modifying call.
            FileExistsError: The snapshot ID already exists.
            ValueError: Metadata, source paths or the configured association ID length is invalid.
        """
        with catalogue_access(self.path_catalogue):
            snapshot = Snapshot(
                id=snap_id,
                name=name,
                desc=desc,
                author=author,
                tags=tags.copy() if tags is not None else [],
                data=dict(data) if data is not None else {},
                directories=build_associations(directory_paths, self.settings.folder_id_length),
            )
            self.add(snapshot, progress_callback=progress_callback, message_callback=message_callback)
            return snapshot

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
        self.delete_with_result(snap, message_callback=message_callback)

    def delete_with_result(self, snap: Snapshot, message_callback: MessageCallback | None = None) -> SnapshotOperationResult:
        """Delete a stored snapshot and report its automatic backup.

        Args:
            snap (Snapshot): Snapshot to delete from the catalogue.
            message_callback (MessageCallback | None): Optional status observer.

        Returns:
            SnapshotOperationResult: Published backup path when a backup was created.
        """
        with catalogue_access(self.path_catalogue):
            snap_manager = self._manager(self._require_snapshot(snap.id))
            backup = None
            if self.settings.bck_before_delete_enabled:
                backup = snap_manager.create_backup(self.settings.backup_path, "beforeDelete", BackupType.SNAPSHOT_DIRECTORY)
            snap_manager.delete(message_callback=message_callback)
            return SnapshotOperationResult(backup)

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

    def get_snapshot_count(self, *, strict: bool = False) -> int:
        """Count published snapshots using the same metadata and recovery rules as get_all().

        Args:
            strict (bool): Propagate filesystem errors when reading catalogue metadata.

        Returns:
            int: Number of snapshots with valid metadata, without scanning association trees or backups.

        Raises:
            SnapshotBusyError: Another operation owns the catalogue.
            OSError: Catalogue storage cannot be read during recovery or strict metadata loading.
        """
        return len(self.get_all(strict=strict))

    def get_statistics(self, *, include_backups: bool = True, strict: bool = False, snapshots: list[Snapshot] | None = None) -> SnapshotCatalogueStatistics:
        """Summarize the published contents of this catalogue after normal snapshot recovery.

        Args:
            include_backups (bool): Count recognized ZIP archives in the configured backup directory. False skips
                all backup I/O and sets backup_count to None.
            strict (bool): Propagate filesystem errors when reading catalogue metadata, as in get_all().
            snapshots (list[Snapshot] | None): Previously loaded snapshots from this catalogue. When supplied,
                calculate statistics for that list without reloading catalogue metadata.

        Returns:
            SnapshotCatalogueStatistics: Counts, logical byte sizes, largest file and creation date range.

        Raises:
            SnapshotBusyError: Another operation owns the catalogue.
            OSError: Catalogue metadata cannot be read in strict mode, a legacy association or the configured backup
                directory cannot be enumerated, or recovery cannot access catalogue storage.
            ValueError: A legacy association contains an unsafe path or a link.

        Notes:
            Counts and byte sizes describe captured association data. Metadata files, backup archives and
            operational directories are outside those totals. Validated manifests supply captured sizes without
            inspecting the stored files. For legacy associations without a manifest, the stored copy is measured
            using file metadata. Legacy scanning errors propagate even in tolerant catalogue mode.
        """
        with catalogue_access(self.path_catalogue, write=False):
            if snapshots is None:
                snapshots = self.get_all(strict=strict)
            backup_count = self._backups().count_backups() if include_backups else None
            return collect_catalogue_statistics(self.path_catalogue, snapshots, backup_count)

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

    def update_snapshot(
        self,
        snap_id: str,
        *,
        name: str | None = None,
        desc: str | None = None,
        tags: list[str] | None = None,
        directory_paths: Sequence[str | Path] | None = None,
        data_updates: Mapping[str, str] | None = None,
        data_remove: Sequence[str] = (),
        message_callback: MessageCallback | None = None,
    ) -> Snapshot:
        """Apply a partial update to the current stored snapshot using the normal edit and backup workflow.

        Args:
            snap_id (str): ID of the snapshot to edit.
            name (str | None): Replacement name; None preserves the current value.
            desc (str | None): Replacement description; None preserves it, an empty string clears it.
            tags (list[str] | None): Replacement tags; None preserves them, an empty list clears them.
            directory_paths (Sequence[str | Path] | None): Complete ordered source list when supplied, including an
                empty list to remove all associations. None leaves associations and their indexes unchanged.
                Paths that identify the same retained directories keep the stored spelling, IDs, and capture metadata.
            data_updates (Mapping[str, str] | None): Custom values to add or replace. Unspecified keys are preserved.
            data_remove (Sequence[str]): Custom keys to remove, ignoring missing keys. Updates take precedence
                when a key is present in both arguments.
            message_callback (MessageCallback | None): Observer receiving one status message at a time.

        Returns:
            Snapshot: Saved snapshot after the edit, including capture metadata for new associations.

        Raises:
            SnapshotBusyError: Another operation owns the catalogue, or an observer attempts a modifying call.
            ValueError: The snapshot cannot be loaded, a field is invalid, or a path is duplicated or ambiguous.
        """
        return self.update_snapshot_with_result(
            snap_id,
            name=name,
            desc=desc,
            tags=tags,
            directory_paths=directory_paths,
            data_updates=data_updates,
            data_remove=data_remove,
            message_callback=message_callback,
        ).snapshot

    def update_snapshot_with_result(
        self,
        snap_id: str,
        *,
        name: str | None = None,
        desc: str | None = None,
        tags: list[str] | None = None,
        directory_paths: Sequence[str | Path] | None = None,
        data_updates: Mapping[str, str] | None = None,
        data_remove: Sequence[str] = (),
        message_callback: MessageCallback | None = None,
    ) -> SnapshotUpdateResult:
        """Apply a partial update and report the saved model and the automatic backup.

        Args:
            snap_id (str): ID of the snapshot to edit.
            name (str | None): Replacement display name.
            desc (str | None): Replacement description.
            tags (list[str] | None): Replacement tags.
            directory_paths (Sequence[str | Path] | None): Complete replacement list of ordered source paths.
            data_updates (Mapping[str, str] | None): Custom values to add or replace.
            data_remove (Sequence[str]): Custom keys to remove before applying updates.
            message_callback (MessageCallback | None): Optional status observer.

        Returns:
            SnapshotUpdateResult: Saved snapshot and published backup path, if created.

        Notes:
            The field and backup rules are the same as in update_snapshot().
        """
        with catalogue_access(self.path_catalogue):
            previous = self.get_by_id(snap_id)
            if previous is None:
                raise ValueError(f"No snapshot found with ID {snap_id}")
            snapshot = configure_snapshot(
                previous,
                self.settings.folder_id_length,
                name=name,
                desc=desc,
                tags=tags,
                directory_paths=directory_paths,
                data_updates=data_updates,
                data_remove=data_remove,
            )
            backup = self._update_snapshot_by_objs(previous, snapshot, message_callback)
            return SnapshotUpdateResult(backup_path=backup, snapshot=snapshot)

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
        self._update_snapshot_by_objs(old, new, message_callback)

    def _update_snapshot_by_objs(self, old: Snapshot, new: Snapshot, message_callback: MessageCallback | None) -> Path | None:
        """Calculate association edits and apply them under the catalogue lock.

        Args:
            old (Snapshot): Current snapshot used for the diff.
            new (Snapshot): Desired snapshot model.
            message_callback (MessageCallback | None): Optional status observer.

        Returns:
            Path | None: Published backup path, if created.
        """
        with catalogue_access(self.path_catalogue):
            edits = SnapshotUtils.get_edits_between_snapshots(old, new)
            return self._update_snapshot_by_edits(new, edits, message_callback)

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
        self._update_snapshot_by_edits(snap, edits, message_callback)

    def _update_snapshot_by_edits(self, snap: Snapshot, edits: list[SnapEditAction], message_callback: MessageCallback | None) -> Path | None:
        """Run the shared backup and edit workflow.

        Args:
            snap (Snapshot): Desired snapshot model.
            edits (list[SnapEditAction]): Association edits to apply.
            message_callback (MessageCallback | None): Optional status observer.

        Returns:
            Path | None: Published backup path, if created.
        """
        with catalogue_access(self.path_catalogue):
            snap_manager = self._manager(snap)
            backup = None
            if self.settings.bck_before_modify_enabled:
                backup = snap_manager.create_backup(self.settings.backup_path, "beforeEdit", BackupType.SNAPSHOT_DIRECTORY)
            snap_manager.snapshot.date_modified = datetime.now()
            snap_manager.snapshot.date_last_modified = datetime.now()
            snap_manager.update_from_actions_list(edits, message_callback=message_callback)
            return backup

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

    def export_captured_assoc_dirs(self, snap_id: str, destination_path: Path, message_callback: MessageCallback | None = None) -> None:
        """Export the captured copies as an associated-directory ZIP.

        Args:
            snap_id (str): ID of the stored snapshot to export.
            destination_path (Path): Folder receiving the completed archive.
            message_callback (MessageCallback | None): Optional per-entry status observer.

        Returns:
            None: The associated-directory archive is written to destination_path.

        Raises:
            SnapshotIncompleteError: A declared captured directory is missing.
            SnapshotBusyError: Another operation owns the catalogue.
        """
        from pylizlib.core.os.snap.operations.backup.creation import BackupCreator

        with catalogue_access(self.path_catalogue):
            storage = self._manager(self._require_snapshot(snap_id))._storage()
            BackupCreator(storage).export_captured_associations(destination_path, message_callback)

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
        self.sync_with_result(snap_id, message_callback=message_callback)

    def sync_with_result(self, snap_id: str, message_callback: MessageCallback | None = None) -> SnapshotOperationResult:
        """Capture current associated folders and report the automatic backup.

        Args:
            snap_id (str): ID of the snapshot whose stored copies are updated.
            message_callback (MessageCallback | None): Optional status observer.

        Returns:
            SnapshotOperationResult: Published backup path when a backup was created.
        """
        with catalogue_access(self.path_catalogue):
            snap = self._require_snapshot(snap_id)

            snap_manager = self._manager(snap)
            backup = None
            if self.settings.bck_before_modify_enabled:
                backup = snap_manager.create_backup(self.settings.backup_path, "beforeUpdateLocal", BackupType.SNAPSHOT_DIRECTORY)
            snap_manager.update_associated_dirs_from_system(message_callback=message_callback)
            return SnapshotOperationResult(backup)

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
            RuntimeError: Legacy installation history is unknown or a previous removal needs review.
            ExceptionGroup: One or more removals or registration updates failed; successful removals stay unregistered.
            NotADirectoryError: A registered destination is no longer a real directory.
            SnapshotIncompleteError: A selected directory cannot be completely backed up; nothing is removed.
            ValueError: Backup storage is not configured or a registered destination is unsafe.
        """
        self.remove_installed_copies_with_result(snap_id, message_callback=message_callback)

    def remove_installed_copies_with_result(self, snap_id: str, message_callback: MessageCallback | None = None) -> SnapshotOperationResult:
        """Remove registered copies and report the backup of their current state.

        Args:
            snap_id (str): ID of the snapshot whose installed copies are removed.
            message_callback (MessageCallback | None): Optional status observer.

        Returns:
            SnapshotOperationResult: Published backup path, or no path when there are no copies to remove.
        """
        with catalogue_access(self.path_catalogue):
            snap = self.get_by_id(snap_id)
            if not snap:
                logger.warning(f"Snapshot with ID '{snap_id}' not found. Cannot remove installed copies.")
                return SnapshotOperationResult(None)
            snap_manager = self._manager(snap)
            backup = snap_manager._remove_installed_copies(message_callback=message_callback)
            return SnapshotOperationResult(backup)

    def get_removable_paths(self, snap_id: str) -> list[Path] | None:
        """Return currently removable installed paths; None marks an untracked legacy snapshot.

        Args:
            snap_id (str): Snapshot ID identifying the catalogue entry.

        Returns:
            list[Path] | None: Existing registered real directories, an empty list when none are installed, or None
                when installation history is unknown.

        Raises:
            NotADirectoryError: A registered destination is no longer a real directory.
            ValueError: Snapshot does not exist or a registered destination fails safety validation.
            RuntimeError: A removal was interrupted and its backup needs review before retrying.
            SnapshotBusyError: Another operation owns the catalogue.
        """
        with catalogue_access(self.path_catalogue):
            snap = self.get_by_id(snap_id)
            if snap is None:
                raise ValueError(f"No snapshot found with ID {snap_id}.")
            return self._manager(snap).get_removable_paths()

    def install(self, snap: Snapshot, clear_destination: bool = True, progress_callback=None, message_callback=None):
        """Installs a snapshot's contents to their original target locations.

        If backup settings are enabled, existing target locations are backed up first. Missing destinations are
        omitted from this preliminary archive and recreated by installation.

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
        self.install_with_result(snap, clear_destination=clear_destination, progress_callback=progress_callback, message_callback=message_callback)

    def install_with_result(
        self,
        snap: Snapshot,
        clear_destination: bool = True,
        progress_callback: SnapshotPercentCallback | None = None,
        message_callback: MessageCallback | None = None,
    ) -> SnapshotOperationResult:
        """Install a snapshot and report the published backup of existing targets.

        Args:
            snap (Snapshot): Snapshot whose latest stored contents are installed.
            clear_destination (bool): Replace the target roots when True, or merge their top-level entries when False.
            progress_callback (SnapshotPercentCallback | None): Optional percentage observer.
            message_callback (MessageCallback | None): Optional status observer.

        Returns:
            SnapshotOperationResult: Published backup path when a backup was created. Missing targets are omitted.
        """
        with catalogue_access(self.path_catalogue):
            stored_snapshot = self.get_by_id(snap.id)
            if stored_snapshot is None:
                raise ValueError(f"No snapshot found with ID {snap.id}.")

            # The caller may hold a model loaded before the snapshot was updated.
            # Installation must use the persisted manifest that matches on-disk data.
            snap_manager = self._manager(stored_snapshot)
            backup = None
            if self.settings.bck_before_install_enabled:
                backup = snap_manager._create_backup_for_existing_associations(
                    self.settings.backup_path,
                    "preinstall",
                )
            snap_manager.install(self.settings.install_with_everyone_full_control, clear_destination=clear_destination, progress_callback=progress_callback, message_callback=message_callback)
            snap.date_last_used = stored_snapshot.date_last_used
            return SnapshotOperationResult(backup)

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
