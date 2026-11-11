"""Synchronize stored snapshot associations from their live system directories."""

import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pylizlib.core.data.gen import gen_random_string
from pylizlib.core.log.pylizLogger import logger
from pylizlib.core.os.snap.domain import SnapDirAssociation
from pylizlib.core.os.snap.integrity import IntegrityManifest
from pylizlib.core.os.snap.storage.context import SnapshotStorage
from pylizlib.core.os.snap.storage.transactions import SnapshotTransactionJournal, prepare_snapshot_metadata, recover_storage_transactions, rename_and_sync
from pylizlib.core.os.utils import get_folder_size_mb


@dataclass(frozen=True)
class SyncReplacement:
    """One successfully staged source and the paths needed for its recovery."""

    snapshot_copy_path: Path
    staging_dir: Path
    backup_dir: Path
    dir_assoc: SnapDirAssociation
    system_path: Path
    had_original: bool


class SnapshotSynchronizer:
    """Refresh stored copies from live directories with persistent crash recovery."""

    def __init__(self, storage: SnapshotStorage):
        """Use the current model, settings and protected metadata adapter."""
        self.storage = storage

    def update_associated_dirs_from_system(self, message_callback=None):
        """
        Updates the snapshot's internal copy of each associated directory
        with the current version from the original system path.
        """
        self.storage.snapshot.validate()
        self.storage.root_path()
        recover_storage_transactions(self.storage)
        self._validate_sources()

        rollbacks = []
        updated_manifests = {}
        original_metadata = {assoc.folder_id: (assoc.integrity_manifest, assoc.mb_size) for assoc in self.storage.snapshot.directories}
        original_date_last_modified = self.storage.snapshot.date_last_modified
        rollbacks = self._plan_replacements()
        journal = SnapshotTransactionJournal.begin(
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
                    for rb in rollbacks
                ],
                "staging_roots": [rb.staging_dir.as_posix() for rb in rollbacks],
            },
        )
        try:
            self._stage_system_copies(rollbacks, updated_manifests, message_callback)
            self._update_model_metadata(rollbacks, updated_manifests)
            metadata = prepare_snapshot_metadata(self.storage, journal.workspace)
            journal.update_payload(metadata=metadata)
            self._replace_stored_copies(rollbacks)
            journal.set_state("commit_decided")
        except Exception as error:
            logger.error(f"Update from system failed during transaction. Rolling back. Reason: {error}")
            try:
                journal.decide_rollback(self.storage)
                self._restore_model_metadata(original_metadata, original_date_last_modified)
            except Exception as rollback_error:
                logger.error(f"Sync rollback is incomplete; journal retained at '{journal.path}': {rollback_error}")
                raise RuntimeError(f"Sync rollback is incomplete; journal retained at '{journal.path}'.") from error
            raise

        try:
            new_metadata = self.storage.metadata.read_bytes(journal.workspace / metadata["new"])
            self.storage.metadata.write_bytes(self.storage.path_snapshot_json, new_metadata)
        except Exception as error:
            if getattr(error, "published", False) is True:
                raise
            try:
                journal.decide_rollback(self.storage)
                self._restore_model_metadata(original_metadata, original_date_last_modified)
            except Exception as rollback_error:
                logger.error(f"Sync rollback is incomplete; journal retained at '{journal.path}': {rollback_error}")
                raise RuntimeError(f"Sync rollback is incomplete; journal retained at '{journal.path}'.") from error
            raise

        journal.set_state("committed")
        journal.finalize([rb.backup_dir for rb in rollbacks] + [rb.staging_dir for rb in rollbacks], "Update from system")

    def _validate_sources(self) -> None:
        """Validate every source before preparing or replacing any stored copy."""
        # Validate all sources before deleting anything
        for dir_assoc in self.storage.snapshot.directories:
            system_path = Path(dir_assoc.original_path)
            if not system_path.exists() or not system_path.is_dir():
                raise FileNotFoundError(f"Original path '{system_path}' for snapshot '{self.storage.snapshot.id}' does not exist or is not a directory. Update aborted.")

    def _plan_replacements(self) -> list[SyncReplacement]:
        """Create the complete same-filesystem swap plan before copying sources."""
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

    def _stage_system_copies(self, rollbacks: list[SyncReplacement], updated_manifests: dict[str, IntegrityManifest], message_callback) -> None:
        """Copy every source to staging and retain each newly captured manifest."""
        for rb in rollbacks:
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


    def _replace_stored_copies(self, rollbacks: list[SyncReplacement]) -> None:
        """Move originals aside and publish the prepared directories in order."""
        # Replace internal copy only at the end
        for rb in rollbacks:
            snap_path = rb.snapshot_copy_path
            staging_dir = rb.staging_dir
            backup_dir = rb.backup_dir

            if rb.had_original:
                rename_and_sync(snap_path, backup_dir)

            rename_and_sync(staging_dir, snap_path)

    def _update_model_metadata(self, rollbacks: list[SyncReplacement], updated_manifests: dict[str, IntegrityManifest]) -> None:
        """Update in-memory manifests and sizes before staging the new JSON."""
        for rb in rollbacks:
            dir_assoc = rb.dir_assoc
            dir_assoc.mb_size = get_folder_size_mb(rb.system_path)
            dir_assoc.integrity_manifest = updated_manifests[dir_assoc.folder_id]

        self.storage.snapshot.date_last_modified = datetime.now()

    def _restore_model_metadata(self, original_metadata: dict, original_date_last_modified: datetime | None) -> None:
        """Restore only in-memory size, manifest and timestamp fields."""
        for assoc in self.storage.snapshot.directories:
            assoc.integrity_manifest, assoc.mb_size = original_metadata[assoc.folder_id]
        self.storage.snapshot.date_last_modified = original_date_last_modified
