"""Execute snapshot-tree and associated-directory restore plans with crash recovery."""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path

from pylizlib.core.log.pylizLogger import logger
from pylizlib.core.os.snap.domain import BackupType, SnapshotBackupInfo, SnapshotSettings
from pylizlib.core.os.snap.operations.archives import SnapshotLookup, _ArchiveMetadata
from pylizlib.core.os.snap.operations.backup.associations import association_identities
from pylizlib.core.os.snap.operations.backup.inspection import BackupArchiveInspector
from pylizlib.core.os.snap.operations.backup.planning import AssociationRestoreTask, RestorePlanner
from pylizlib.core.os.snap.operations.backup_names import parse_backup_filename
from pylizlib.core.os.snap.serializer import SnapshotSerializer
from pylizlib.core.os.snap.storage.archives import extract_zip, validate_zip_archive
from pylizlib.core.os.snap.storage.paths import assert_no_transaction_storage
from pylizlib.core.os.snap.storage.publication import publish_snapshot_tree
from pylizlib.core.os.snap.storage.recovery.models import ReplacementEntry
from pylizlib.core.os.snap.storage.transactions import SnapshotTransactionJournal, recover_pending_transactions, rename_and_sync
from pylizlib.core.os.snap.storage.tree import assert_no_symlinks


class SnapshotTreeRestorer:
    """Verify and publish the stored tree of an SD backup.

    Attributes:
        path_catalogue (Path): Catalogue root retained by this collaborator.
        settings (SnapshotSettings): Mutable snapshot settings retained by reference; no defensive copy is made.
    """

    def __init__(self, path_catalogue: Path, settings: SnapshotSettings):
        """Bind snapshot-tree publication policy.

        Args:
            path_catalogue (Path): Catalogue root retained by this collaborator.
            settings (SnapshotSettings): Mutable snapshot settings retained by reference; no defensive copy is made.

        Returns:
            None: No return value.
        """
        self.path_catalogue = path_catalogue
        self.settings = settings

    def restore(self, temp_dir_path: Path, metadata: _ArchiveMetadata) -> None:
        """Replace a complete snapshot root after checking its embedded identity and associations.

        Args:
            temp_dir_path (Path): Extraction root owned by the surrounding temporary-directory context.
            metadata (_ArchiveMetadata): Validated archive interpretation or staged JSON names used by this operation.

        Returns:
            None: No return value.

        Raises:
            ValueError: A value, path, resource limit or metadata field violates the validation rules described above.
        """
        assert_no_transaction_storage(temp_dir_path)
        json_path = temp_dir_path / self.settings.json_filename
        if not json_path.is_file():
            raise ValueError(f"Snapshot-directory backup does not contain '{self.settings.json_filename}'.")

        restored_snapshot = SnapshotSerializer.from_json(json_path)
        if metadata.info.snapshot_id is not None and restored_snapshot.id != metadata.info.snapshot_id:
            raise ValueError("Snapshot-directory JSON ID does not match the archive metadata.")
        if metadata.associations is not None:
            archived_associations = association_identities(metadata.associations)
            snapshot_associations = association_identities(restored_snapshot.directories)
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


class AssociationRestorer:
    """Stage every AD copy before publishing targets under the existing journal.

    Attributes:
        planner (RestorePlanner): Restore planner owning current settings, catalogue scope and legacy metadata
            lookup.
        path_catalogue (Path): Catalogue root retained by this collaborator.
        settings (SnapshotSettings): Mutable snapshot settings retained by reference; no defensive copy is made.
    """

    def __init__(self, planner: RestorePlanner):
        """Reuse the planner's current settings, lookup and catalogue scope.

        Args:
            planner (RestorePlanner): Restore planner owning current settings, catalogue scope and legacy metadata
                lookup.

        Returns:
            None: No return value.
        """
        self.planner = planner
        self.path_catalogue = planner.path_catalogue
        self.settings = planner.settings

    def restore(self, metadata: _ArchiveMetadata, temp_dir_path: Path, destination_mapping: Mapping[str, str | Path] | None = None) -> None:
        """Revalidate extracted AD contents and execute the resulting plan.

        Args:
            metadata (_ArchiveMetadata): Validated archive interpretation or staged JSON names used by this operation.
            temp_dir_path (Path): Extraction root owned by the surrounding temporary-directory context.
            destination_mapping (Mapping[str, str | Path] | None): Overrides keyed by stable folder_id; unmapped AD
                associations retain their archived source paths.

        Returns:
            None: No return value.
        """
        associations, origin_os = self.planner.associations_from(metadata)
        tasks = self.planner.build(temp_dir_path, associations, destination_mapping, metadata.manifest_name, origin_os)
        self.execute(tasks)

    def execute(self, tasks: list[AssociationRestoreTask]) -> None:
        """Persist recovery paths, stage every copy, publish, then finalize.

        Args:
            tasks (list[AssociationRestoreTask]): Complete AD restore plan with distinct extracted source, sibling
                staging, target and backup paths.

        Returns:
            None: No return value.

        Notes:
            Every owned path is journaled before copying. All copies finish before the first destination swap. Failure
            follows the existing rollback decision, while final cleanup runs only after committed state.
        """
        journal = SnapshotTransactionJournal.begin(self.path_catalogue, "restore_associations_manifest", {"entries": []})

        # Journal all owned paths before creating the first staging copy.
        try:
            entries: list[ReplacementEntry] = [
                {"folder_id": task.folder_id, "stage": task.staged_dir.as_posix(), "destination": task.destination.as_posix(), "backup": task.backup_dest.as_posix(), "had_original": task.had_original}
                for task in tasks
            ]
            journal.update_payload(entries=entries)

            # Complete every copy before making the first target visible.
            self._stage_copies(tasks)
            self._publish_copies(tasks)

            # Preserve the two existing durable decisions before cleanup.
            journal.set_state("commit_decided")
            journal.set_state("committed")
        except Exception as e:
            logger.error(f"Failed to restore associated directories: {e}. Rolling back.")
            try:
                journal.decide_rollback()
            except Exception as rollback_error:
                e.add_note(f"Persistent recovery journal retained at '{journal.path}': {rollback_error}")
            raise IOError(f"Failed to restore associated directories: {e}") from e

        journal.finalize([path for task in tasks for path in (task.backup_dest, task.staged_dir)], "Associated-directories restore")

    def _stage_copies(self, tasks: list[AssociationRestoreTask]) -> None:
        """Copy validated extracted roots to their target-volume staging siblings.

        Args:
            tasks (list[AssociationRestoreTask]): Complete AD restore plan with distinct extracted source, sibling
                staging, target and backup paths.

        Returns:
            None: No return value.
        """
        for task in tasks:
            assert_no_symlinks(task.extracted_dir)
            self.settings.copy_strategy.copy_directory(task.extracted_dir, task.staged_dir)
            assert_no_symlinks(task.staged_dir)

    @staticmethod
    def _publish_copies(tasks: list[AssociationRestoreTask]) -> None:
        """Swap staged trees in association order while preserving every original.

        Args:
            tasks (list[AssociationRestoreTask]): Complete AD restore plan with distinct extracted source, sibling
                staging, target and backup paths.

        Returns:
            None: No return value.

        Raises:
            FileNotFoundError: A required source, stored association or metadata entry is absent.
            FileExistsError: A destination or generated staging name already exists or changes before publication.
        """
        for task in tasks:
            destination = task.destination
            if task.had_original:
                if not (destination.exists() or destination.is_symlink()):
                    raise FileNotFoundError(f"Restore destination '{destination}' disappeared before publication.")
                rename_and_sync(destination, task.backup_dest)
            elif destination.exists() or destination.is_symlink():
                raise FileExistsError(f"Restore destination '{destination}' appeared before publication.")
            rename_and_sync(task.staged_dir, destination)


class BackupRestorer:
    """Coordinate preflight, temporary-volume choice, extraction and AD/SD dispatch.

    Attributes:
        path_catalogue (Path): Catalogue root retained by this collaborator.
        settings (SnapshotSettings): Mutable snapshot settings retained by reference; no defensive copy is made.
        planner (RestorePlanner): Restore planner owning current settings, catalogue scope and legacy metadata
            lookup.
        inspector (BackupArchiveInspector): Backup-format inspector preserving modern/legacy precedence.
        tree_restorer (SnapshotTreeRestorer): SD stored-tree publication coordinator.
        association_restorer (AssociationRestorer): AD staging/publication coordinator using the shared
            destination planner.
        extractor (Callable): Extraction hook accepting the configured ZIP limits and additional byte
            requirements.
    """

    def __init__(
        self, path_catalogue: Path, settings: SnapshotSettings, lookup: SnapshotLookup, parse_info: Callable[[Path], SnapshotBackupInfo] = parse_backup_filename, *, extractor: Callable = extract_zip
    ):
        """Bind collaborators while retaining the caller's parser and extraction hooks.

        Args:
            path_catalogue (Path): Catalogue root retained by this collaborator.
            settings (SnapshotSettings): Mutable snapshot settings retained by reference; no defensive copy is made.
            lookup (SnapshotLookup): Catalogue lookup capability used when legacy archive metadata needs a persisted
                snapshot.
            parse_info (Callable[[Path], SnapshotBackupInfo]): Legacy filename parser hook; embedded metadata
                overrides filename identity and type.
            extractor (Callable): Extraction hook accepting the configured ZIP limits and additional byte
                requirements.

        Returns:
            None: No return value.
        """
        self.path_catalogue = path_catalogue
        self.settings = settings
        self.planner = RestorePlanner(path_catalogue, settings, lookup)
        self.inspector = BackupArchiveInspector(settings, parse_info)
        self.tree_restorer = SnapshotTreeRestorer(path_catalogue, settings)
        self.association_restorer = AssociationRestorer(self.planner)
        self.extractor = extractor

    def restore(self, backup_zip_path: Path, destination_mapping: Mapping[str, str | Path] | None) -> None:
        """Validate, extract and dispatch one archive, with optional AD remapping.

        Args:
            backup_zip_path (Path): Backup archive path; embedded metadata takes precedence over legacy filename
                hints.
            destination_mapping (Mapping[str, str | Path] | None): Overrides keyed by stable folder_id; unmapped AD
                associations retain their archived source paths.

        Returns:
            None: No return value.

        Raises:
            ValueError: A value, path, resource limit or metadata field violates the validation rules described above.
            FileNotFoundError: A required source, stored association or metadata entry is absent.

        Notes:
            Preflight may use catalogue lookup for legacy metadata and selects extraction space before copying. AD
            policy is revalidated after extraction; destination mapping does not bypass originating-OS checks. SD
            mapping is rejected.
        """
        recover_pending_transactions(self.path_catalogue)
        if not backup_zip_path.is_file():
            raise ValueError(f"Provided path '{backup_zip_path}' is not a file.")

        preflight = validate_zip_archive(
            backup_zip_path,
            max_entries=self.settings.max_archive_entries,
            max_uncompressed_bytes=self.settings.max_archive_uncompressed_bytes,
        )
        metadata = self.inspector.read(backup_zip_path)
        info = metadata.info
        if info.backup_type is None:
            raise ValueError("Could not recognize backup type from archive metadata or legacy filename.")
        if info.backup_type == BackupType.SNAPSHOT_DIRECTORY and destination_mapping is not None:
            raise ValueError("Destination remapping is only supported for associated-directories backups.")

        logger.info("Restoring backup snapshot=%s type=%s", info.snapshot_id, info.backup_type.name)
        restore_space_requirements = []
        if info.backup_type == BackupType.ASSOCIATED_DIRECTORIES:
            associations, origin_os = self.planner.associations_from(metadata)
            destinations = self.planner.resolve_destinations(associations, destination_mapping, origin_os)
            for association, destination in zip(associations, destinations, strict=True):
                if not destination.parent.is_dir():
                    raise FileNotFoundError(f"Parent directory for restore destination '{destination}' does not exist.")
                required_bytes = preflight.bytes_by_root.get(association.directory_name, 0)
                restore_space_requirements.append((destination.parent, required_bytes))
        else:
            restore_space_requirements.append((self.path_catalogue, preflight.uncompressed_bytes))

        temp_parent = self.settings.archive_temp_directory

        # Put the extracted archive on a destination volume by default so a
        # large AD restore does not need equivalent space under system temp.
        if temp_parent is None and info.backup_type == BackupType.ASSOCIATED_DIRECTORIES and destinations:
            temp_parent = max((destination.parent for destination in destinations), key=lambda path: shutil.disk_usage(path).free)
        if temp_parent is None:
            temp_parent = self.path_catalogue
        temp_parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".archive_staging_", dir=temp_parent) as temp_dir:
            temp_dir_path = Path(temp_dir)
            self.extractor(
                backup_zip_path,
                temp_dir_path,
                max_entries=self.settings.max_archive_entries,
                max_uncompressed_bytes=self.settings.max_archive_uncompressed_bytes,
                additional_space_requirements=restore_space_requirements,
            )

            if info.backup_type == BackupType.SNAPSHOT_DIRECTORY:
                self.tree_restorer.restore(temp_dir_path, metadata)
            else:
                self.association_restorer.restore(metadata, temp_dir_path, destination_mapping)

        logger.info("Restored backup snapshot=%s type=%s", info.snapshot_id, info.backup_type.name)
