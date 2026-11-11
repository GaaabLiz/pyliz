"""Lifecycle operations on complete stored snapshot trees."""

import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from pylizlib.core.data.gen import gen_random_string
from pylizlib.core.os.path import remove_directory_or_move_to_temp
from pylizlib.core.os.snap.domain import validate_directory_component
from pylizlib.core.os.snap.storage.context import SnapshotStorage
from pylizlib.core.os.snap.storage.publication import cleanup_after_commit, publish_snapshot_tree


class SnapshotLifecycle:
    """Create, delete and duplicate snapshot roots using existing publication rules."""

    def __init__(self, storage: SnapshotStorage):
        """Bind the live model and its originally captured snapshot destinations."""
        self.storage = storage

    def create(self, progress_callback=None, message_callback=None, *, replace_existing: bool = False):
        """
        Creates the snapshot by preparing its contents and metadata in staging.

        Existing IDs are rejected unless replace_existing=True. An explicit
        replacement retains the old directory until publication succeeds and
        restores it if publication fails. Cleanup runs after commit.

        Raises:
            FileExistsError: If the destination exists and replacement is disabled.
        """
        self.storage.snapshot.validate()
        validate_directory_component(self.storage.settings.json_filename, "Snapshot JSON filename")
        self.storage.root_path()
        if not replace_existing and (self.storage.path_snapshot.exists() or self.storage.path_snapshot.is_symlink()):
            raise FileExistsError(f"Snapshot destination '{self.storage.path_snapshot}' already exists.")

        self.storage.path_catalogue.mkdir(parents=True, exist_ok=True)
        transaction_path = Path(tempfile.mkdtemp(prefix=f"_staging_create_{self.storage.snapshot.id}_", dir=self.storage.path_catalogue))
        staging_path = transaction_path / "new"
        backup_path = transaction_path / "original"
        original_moved = False
        previous_manifests = {assoc.folder_id: assoc.integrity_manifest for assoc in self.storage.snapshot.directories}
        try:
            staging_path.mkdir()

            self._stage_associations(staging_path, progress_callback, message_callback)

            # Write json to staging BEFORE making it the final destination
            json_path = staging_path / validate_directory_component(self.storage.settings.json_filename, "Snapshot JSON filename")
            self.storage.metadata.to_json(self.storage.snapshot, json_path)

            if self.storage.path_snapshot.exists() or self.storage.path_snapshot.is_symlink():
                if not replace_existing:
                    raise FileExistsError(f"Snapshot destination '{self.storage.path_snapshot}' already exists.")
                self.storage.path_snapshot.rename(backup_path)
                original_moved = True
            staging_path.rename(self.storage.path_snapshot)
        except Exception:
            for assoc in self.storage.snapshot.directories:
                assoc.integrity_manifest = previous_manifests[assoc.folder_id]
            if original_moved:
                # If rollback itself fails, preserve both copies in the
                # transaction directory instead of deleting recoverable data.
                backup_path.rename(self.storage.path_snapshot)
            shutil.rmtree(transaction_path, ignore_errors=True)
            raise

        cleanup_after_commit([transaction_path], "Snapshot creation")

    def delete(self, message_callback=None):
        """
        Deletes the snapshot's directory, propagating filesystem failures.
        """
        remove_directory_or_move_to_temp(self.storage.root_path(), message_callback=message_callback)

    def duplicate(self, message_callback=None):
        """
        Creates a duplicate of the current snapshot with a new ID and name.
        The entire snapshot directory is copied, and a new JSON file is created for the copy.

        Raises:
            FileNotFoundError: If the original snapshot path does not exist.
        """
        self.storage.root_path()
        if not self.storage.path_snapshot.exists():
            raise FileNotFoundError(f"The snapshot path {self.storage.path_snapshot} does not exist.")
        new_snap = self.storage.snapshot.clone()
        new_snap.id = gen_random_string(self.storage.settings.snap_id_length)
        new_snap.name = self.storage.snapshot.name + " Copy"
        new_snap.date_created = datetime.now()

        def prepare_duplicate(staging_path: Path) -> None:
            json_path = staging_path / validate_directory_component(self.storage.settings.json_filename, "Snapshot JSON filename")
            self.storage.metadata.to_json(new_snap, json_path)

        publish_snapshot_tree(
            self.storage.root_path(),
            new_snap.folder_name,
            self.storage.path_catalogue,
            prepare_staging=prepare_duplicate,
            copy_strategy=self.storage.settings.copy_strategy,
            message_callback=message_callback,
            operation="Snapshot duplication",
        )

    def _stage_associations(self, staging_path: Path, progress_callback, message_callback) -> None:
        """Capture every association and its manifest before writing staged metadata.

        Always supply the copy progress adapter, including when the caller has
        no observer: the original create flow still performs its byte scan.
        """
        # We need to distribute the progress among directories if there are multiple.
        total_dirs = len(self.storage.snapshot.directories)
        for i, snap_dir in enumerate(self.storage.snapshot.directories):

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
                copy_strategy=self.storage.settings.copy_strategy,
                manifest=manifest,
            )
            snap_dir.integrity_manifest = manifest
