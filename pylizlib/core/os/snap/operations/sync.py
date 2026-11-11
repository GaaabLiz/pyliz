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
from pylizlib.core.os.snap.storage.publication import cleanup_after_commit
from pylizlib.core.os.utils import get_folder_size_mb


@dataclass(frozen=True)
class SyncReplacement:
    """One successfully staged source and the paths needed for its recovery."""

    snapshot_copy_path: Path
    staging_dir: Path
    backup_dir: Path
    dir_assoc: SnapDirAssociation
    system_path: Path


class SnapshotSynchronizer:
    """Refresh stored copies from live directories while retaining old backups.

    Metadata restoration intentionally keeps the existing in-memory semantics;
    it does not add the byte-level JSON recovery used by the edit operation.
    """

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
        self._validate_sources()

        rollbacks = []
        updated_manifests = {}
        original_metadata = {assoc.folder_id: (assoc.integrity_manifest, assoc.mb_size) for assoc in self.storage.snapshot.directories}
        original_date_last_modified = self.storage.snapshot.date_last_modified
        try:
            self._stage_system_copies(rollbacks, updated_manifests, message_callback)

            self._replace_stored_copies(rollbacks)

            self._update_metadata(rollbacks, updated_manifests)

        except Exception as e:
            logger.error(f"Update from system failed during transaction. Rolling back. Reason: {e}")
            self._rollback_sync(rollbacks, original_metadata, original_date_last_modified)
            raise

        cleanup_after_commit((rb.backup_dir for rb in rollbacks), "Update from system")

    def _validate_sources(self) -> None:
        """Validate every source before preparing or replacing any stored copy."""
        # Validate all sources before deleting anything
        for dir_assoc in self.storage.snapshot.directories:
            system_path = Path(dir_assoc.original_path)
            if not system_path.exists() or not system_path.is_dir():
                raise FileNotFoundError(f"Original path '{system_path}' for snapshot '{self.storage.snapshot.id}' does not exist or is not a directory. Update aborted.")

    def _stage_system_copies(self, rollbacks: list[SyncReplacement], updated_manifests: dict[str, IntegrityManifest], message_callback) -> None:
        """Copy every source to staging and retain each newly captured manifest."""
        for dir_assoc in self.storage.snapshot.directories:
            system_path = Path(dir_assoc.original_path)
            snapshot_copy_path = self.storage.child_path(dir_assoc.directory_name)

            # Copy each source to staging
            staging_dir = self.storage.child_path(f"{dir_assoc.directory_name}_staging_{gen_random_string(6)}")
            backup_dir = self.storage.child_path(f"{dir_assoc.directory_name}_bck_{gen_random_string(6)}")

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

            rollbacks.append(SyncReplacement(snapshot_copy_path, staging_dir, backup_dir, dir_assoc, system_path))

    def _replace_stored_copies(self, rollbacks: list[SyncReplacement]) -> None:
        """Move originals aside and publish the prepared directories in order."""
        # Replace internal copy only at the end
        for rb in rollbacks:
            snap_path = rb.snapshot_copy_path
            staging_dir = rb.staging_dir
            backup_dir = rb.backup_dir

            if snap_path.exists():
                snap_path.rename(backup_dir)

            staging_dir.rename(snap_path)

    def _update_metadata(self, rollbacks: list[SyncReplacement], updated_manifests: dict[str, IntegrityManifest]) -> None:
        """Measure live source sizes and save manifests while backups remain intact."""
        # Update metadata while backups are still intact.
        for rb in rollbacks:
            dir_assoc = rb.dir_assoc
            dir_assoc.mb_size = get_folder_size_mb(rb.system_path)
            dir_assoc.integrity_manifest = updated_manifests[dir_assoc.folder_id]

        self.storage.snapshot.date_last_modified = datetime.now()
        self.storage.save_json()

    def _rollback_sync(self, rollbacks: list[SyncReplacement], original_metadata: dict, original_date_last_modified: datetime | None) -> None:
        """Restore available backups and the original in-memory sizes, manifests and date."""
        for rb in rollbacks:
            snap_path = rb.snapshot_copy_path
            staging_dir = rb.staging_dir
            backup_dir = rb.backup_dir

            if staging_dir.exists():
                shutil.rmtree(staging_dir)

            if backup_dir.exists():
                if snap_path.exists():
                    shutil.rmtree(snap_path)
                backup_dir.rename(snap_path)
        for assoc in self.storage.snapshot.directories:
            assoc.integrity_manifest, assoc.mb_size = original_metadata[assoc.folder_id]
        self.storage.snapshot.date_last_modified = original_date_last_modified
