"""Synchronize stored snapshot associations from their live system directories."""

import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from pylizlib.core.data.gen import gen_random_string
from pylizlib.core.log.pylizLogger import logger
from pylizlib.core.os.snap.domain import SnapDirAssociation
from pylizlib.core.os.snap.integrity import IntegrityManifest
from pylizlib.core.os.snap.model_state import CapturedContentState
from pylizlib.core.os.snap.storage.context import SnapshotStorage
from pylizlib.core.os.snap.storage.transactions import SnapshotTransactionJournal, prepare_snapshot_metadata, recover_storage_transactions, rename_and_sync
from pylizlib.core.os.snap.storage.tree import assert_no_symlinks


@dataclass(frozen=True)
class SyncReplacement:
    """One successfully staged source and the paths needed for its recovery.

    Attributes:
        snapshot_copy_path (Path): Existing stored association directory replaced by synchronization.
        staging_dir (Path): Generated sibling receiving copied contents before publication.
        backup_dir (Path): Directory whose valid ZIP contents should be listed, independent of filename extension.
        dir_assoc (SnapDirAssociation): Directory association whose stored contents or installed copy is operated
            on.
        system_path (Path): Live original source read during synchronization.
        had_original (bool): Whether planning observed a preexisting target; publication still checks concurrent
            changes.
    """

    snapshot_copy_path: Path
    staging_dir: Path
    backup_dir: Path
    dir_assoc: SnapDirAssociation
    system_path: Path
    had_original: bool


class SnapshotSynchronizer:
    """Refresh stored copies from live directories with persistent crash recovery.

    Attributes:
        storage (SnapshotStorage): Live snapshot model, settings, captured layout and protected metadata adapter
            for this operation.
    """

    def __init__(self, storage: SnapshotStorage):
        """Use the current model, settings and protected metadata adapter.

        Args:
            storage (SnapshotStorage): Live snapshot model, settings, captured layout and protected metadata adapter
                for this operation.

        Returns:
            None: No return value.
        """
        self.storage = storage

    def update_associated_dirs_from_system(self, message_callback=None):
        """Updates the snapshot's internal copy of each associated directory
        with the current version from the original system path.

        Args:
            message_callback (MessageCallback | None): Optional status observer receiving one message string; its
                exceptions propagate according to the calling operation.

        Returns:
            None: No return value.

        Notes:
            Rollback before publication restores captured manifests, sizes, capture interval and date_last_modified
            only. A metadata error reporting published=True preserves the newly published state and propagates instead
            of undoing its contents.
        """
        self.storage.snapshot.validate()
        self.storage.root_path()
        recover_storage_transactions(self.storage)
        self._validate_sources()
        logger.info("Synchronizing snapshot id=%s associations=%s", self.storage.snapshot.id, len(self.storage.snapshot.directories))

        updated_manifests = {}
        previous_state = CapturedContentState.capture(self.storage.snapshot)
        original_date_last_modified = self.storage.snapshot.date_last_modified
        replacements = self._plan_replacements()
        journal = self._begin_sync_journal(replacements)
        try:
            self.storage.snapshot.capture_started_at = datetime.now(timezone.utc)
            self.storage.snapshot.capture_completed_at = None
            self._stage_system_copies(replacements, updated_manifests, message_callback)
            self._update_model_metadata(replacements, updated_manifests)
            metadata = prepare_snapshot_metadata(self.storage, journal.workspace)
            journal.update_payload(metadata=metadata)
            self._replace_stored_copies(replacements)
            journal.set_state("commit_decided")
        except Exception as error:
            logger.error(f"Update from system failed during transaction. Rolling back. Reason: {error}")
            self._rollback_failed_sync(journal, previous_state, original_date_last_modified, error)
            raise

        try:
            new_metadata = self.storage.metadata.read_bytes(journal.workspace / metadata["new"])
            self.storage.metadata.write_bytes(self.storage.path_snapshot_json, new_metadata)
        except Exception as error:
            if getattr(error, "published", False) is True:
                raise
            self._rollback_failed_sync(journal, previous_state, original_date_last_modified, error)
            raise

        journal.set_state("committed")
        journal.finalize([rb.backup_dir for rb in replacements] + [rb.staging_dir for rb in replacements], "Update from system")
        logger.info("Synchronized snapshot id=%s", self.storage.snapshot.id)

    def _validate_sources(self) -> None:
        """Validate every source before preparing or replacing any stored copy.

        Returns:
            None: No return value.

        Raises:
            FileNotFoundError: A required source, stored association or metadata entry is absent.
        """

        # Validate all sources before deleting anything
        for dir_assoc in self.storage.snapshot.directories:
            system_path = Path(dir_assoc.original_path)
            if not system_path.exists() or not system_path.is_dir():
                raise FileNotFoundError(f"Original path '{system_path}' for snapshot '{self.storage.snapshot.id}' does not exist or is not a directory. Update aborted.")
            assert_no_symlinks(system_path)

    def _plan_replacements(self) -> list[SyncReplacement]:
        """Create the complete same-filesystem swap plan before copying sources.

        Returns:
            list[SyncReplacement]: Ordered generated staging/backup/target plan; names are checked but not reserved
                against concurrent writers.

        Raises:
            FileExistsError: A destination or generated staging name already exists or changes before publication.
            FileNotFoundError: A required source, stored association or metadata entry is absent.
        """
        replacements = []
        for dir_assoc in self.storage.snapshot.directories:
            snapshot_copy_path = self.storage.child_path(dir_assoc.directory_name)
            staging_dir = self.storage.child_path(f"{dir_assoc.directory_name}_staging_{gen_random_string(6)}")
            backup_dir = self.storage.child_path(f"{dir_assoc.directory_name}_bck_{gen_random_string(6)}")
            if staging_dir.exists() or backup_dir.exists():
                raise FileExistsError(f"Could not reserve sync staging names for '{snapshot_copy_path}'.")
            if not snapshot_copy_path.is_dir():
                raise FileNotFoundError(f"Snapshot association directory '{snapshot_copy_path}' is missing.")
            replacements.append(SyncReplacement(snapshot_copy_path, staging_dir, backup_dir, dir_assoc, Path(dir_assoc.original_path), True))
        return replacements

    def _stage_system_copies(self, replacements: list[SyncReplacement], updated_manifests: dict[str, IntegrityManifest], message_callback) -> None:
        """Copy every source to staging and retain each newly captured manifest.

        Args:
            replacements (list[SyncReplacement]): Complete ordered replacement plan, including target, staging and
                backup paths.
            updated_manifests (dict[str, IntegrityManifest]): Newly captured integrity mappings indexed by stable
                association ID.
            message_callback (MessageCallback | None): Optional status observer receiving one message string; its
                exceptions propagate according to the calling operation.

        Returns:
            None: No return value.

        Raises:
            RuntimeError: The requested operation cannot complete; a wrapped failure retains its original cause where
                documented.
        """
        for rb in replacements:
            dir_assoc = rb.dir_assoc
            system_path = rb.system_path
            staging_dir = rb.staging_dir

            logger.info(f"Copying '{system_path}' to staging '{staging_dir}'")

            try:
                updated_manifests[dir_assoc.folder_id] = {}
                self.storage.settings.copy_strategy.copy_directory(
                    system_path,
                    staging_dir,
                    message_callback=message_callback,
                    manifest=updated_manifests[dir_assoc.folder_id],
                )
            except Exception as e:
                if staging_dir.exists():
                    shutil.rmtree(staging_dir)
                raise RuntimeError(f"Failed to copy system path '{system_path}' to staging '{staging_dir}': {e}") from e

    def _replace_stored_copies(self, replacements: list[SyncReplacement]) -> None:
        """Move originals aside and publish the prepared directories in order.

        Args:
            replacements (list[SyncReplacement]): Complete ordered replacement plan, including target, staging and
                backup paths.

        Returns:
            None: No return value.
        """

        # Replace internal copy only at the end
        for rb in replacements:
            snap_path = rb.snapshot_copy_path
            staging_dir = rb.staging_dir
            backup_dir = rb.backup_dir

            if rb.had_original:
                rename_and_sync(snap_path, backup_dir)

            rename_and_sync(staging_dir, snap_path)

    def _update_model_metadata(self, replacements: list[SyncReplacement], updated_manifests: dict[str, IntegrityManifest]) -> None:
        """Update in-memory manifests and sizes before staging the new JSON.

        Args:
            replacements (list[SyncReplacement]): Complete ordered replacement plan, including target, staging and
                backup paths.
            updated_manifests (dict[str, IntegrityManifest]): Newly captured integrity mappings indexed by stable
                association ID.

        Returns:
            None: No return value.
        """
        for rb in replacements:
            dir_assoc = rb.dir_assoc
            dir_assoc.record_captured_content(updated_manifests[dir_assoc.folder_id])

        self.storage.snapshot.date_last_modified = datetime.now()
        self.storage.snapshot.capture_completed_at = datetime.now(timezone.utc)

    def _restore_model_metadata(
        self,
        original_metadata: dict,
        original_date_last_modified: datetime | None,
        original_capture_times: tuple[datetime | None, datetime | None],
    ) -> None:
        """Restore only in-memory size, manifest and timestamp fields.

        Args:
            original_metadata (dict): Previous (integrity manifest reference, MiB size) pairs indexed by association
                ID.
            original_date_last_modified (datetime | None): Previous local/naive-compatible synchronization
                modification date, or None.
            original_capture_times (tuple[datetime | None, datetime | None]): Prior acquisition start/completion
                values, restored without timezone conversion.

        Returns:
            None: No return value.
        """
        for assoc in self.storage.snapshot.directories:
            assoc.integrity_manifest, assoc.mb_size = original_metadata[assoc.folder_id]
        self.storage.snapshot.date_last_modified = original_date_last_modified
        self.storage.snapshot.capture_started_at, self.storage.snapshot.capture_completed_at = original_capture_times

    def _rollback_failed_sync(self, journal: SnapshotTransactionJournal, previous_state: CapturedContentState, previous_modified: datetime | None, error: Exception) -> None:
        """Rollback data and only the acquisition fields changed by synchronization.

        Args:
            journal (SnapshotTransactionJournal): Transaction journal owning staged paths, persisted decisions and
                cleanup.
            previous_state (CapturedContentState): Prior captured-content state, preserving original manifest
                references and acquisition times.
            previous_modified (datetime | None): Previous sync date_last_modified; restored separately from capture
                fields.
            error (Exception): Original failure to propagate or preserve as the cause of a rollback failure.

        Returns:
            None: No return value.

        Raises:
            RuntimeError: The requested operation cannot complete; a wrapped failure retains its original cause where
                documented.
        """
        try:
            journal.decide_rollback(self.storage)
            self._restore_model_metadata(previous_state.association_metadata, previous_modified, previous_state.capture_times)
        except Exception as rollback_error:
            logger.error(f"Sync rollback is incomplete; journal retained at '{journal.path}': {rollback_error}")
            raise RuntimeError(f"Sync rollback is incomplete; journal retained at '{journal.path}'.") from error

    def _begin_sync_journal(self, replacements: list[SyncReplacement]) -> SnapshotTransactionJournal:
        """Persist the complete ordered swap plan before source capture begins.

        Args:
            replacements (list[SyncReplacement]): Complete ordered replacement plan, including target, staging and
                backup paths.

        Returns:
            SnapshotTransactionJournal: Prepared v1 journal containing every sync replacement and staging root before
                acquisition begins.
        """
        return SnapshotTransactionJournal.begin(
            self.storage.path_snapshot,
            "sync",
            {
                "entries": [
                    {
                        "folder_id": rb.dir_assoc.folder_id,
                        "stage": rb.staging_dir.as_posix(),
                        "destination": rb.snapshot_copy_path.as_posix(),
                        "backup": rb.backup_dir.as_posix(),
                        "had_original": rb.had_original,
                    }
                    for rb in replacements
                ],
                "staging_roots": [rb.staging_dir.as_posix() for rb in replacements],
            },
        )
