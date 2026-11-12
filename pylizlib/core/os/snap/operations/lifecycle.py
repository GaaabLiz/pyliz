"""Lifecycle operations on complete stored snapshot trees."""

from datetime import datetime, timezone
from pathlib import Path

from pylizlib.core.data.gen import gen_random_string
from pylizlib.core.log.pylizLogger import logger
from pylizlib.core.os.path import remove_directory_or_move_to_temp
from pylizlib.core.os.snap.callbacks import report_directory_progress
from pylizlib.core.os.snap.domain import validate_directory_component
from pylizlib.core.os.snap.model_state import CapturedContentState
from pylizlib.core.os.snap.storage.context import SnapshotStorage
from pylizlib.core.os.snap.storage.publication import publish_snapshot_tree, validate_staged_snapshot_tree
from pylizlib.core.os.snap.storage.transactions import SnapshotTransactionJournal, recover_storage_transactions, rename_and_sync
from pylizlib.core.os.snap.storage.tree import assert_destination_outside_source


class SnapshotLifecycle:
    """Create, delete and duplicate snapshot roots using existing publication rules.

    Attributes:
        storage (SnapshotStorage): Live snapshot model, settings, captured layout and protected metadata adapter
            for this operation.
    """

    def __init__(self, storage: SnapshotStorage):
        """Bind the live model and its originally captured snapshot destinations.

        Args:
            storage (SnapshotStorage): Live snapshot model, settings, captured layout and protected metadata adapter
                for this operation.

        Returns:
            None: No return value.
        """
        self.storage = storage

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

        Notes:
            Progress is equal-directory-weight integer percentage; an empty snapshot reports 100 once. With no
            observer, no preliminary byte-total scan is introduced. Captured times use aware UTC; name/date_created
            defaults remain unchanged.
        """
        self.storage.snapshot.validate()
        validate_directory_component(self.storage.settings.json_filename, "Snapshot JSON filename")
        self.storage.root_path()
        for association in self.storage.snapshot.directories:
            assert_destination_outside_source(association.original_path, self.storage.path_catalogue)
        self.storage.path_catalogue.mkdir(parents=True, exist_ok=True)
        recover_storage_transactions(self.storage)
        if not replace_existing and (self.storage.path_snapshot.exists() or self.storage.path_snapshot.is_symlink()):
            raise FileExistsError(f"Snapshot destination '{self.storage.path_snapshot}' already exists.")

        had_original = self.storage.path_snapshot.exists() or self.storage.path_snapshot.is_symlink()
        journal = SnapshotTransactionJournal.begin(
            self.storage.path_catalogue,
            "snapshot_tree",
            {"snapshot_id": self.storage.snapshot.id, "had_original": had_original},
        )
        transaction_path = journal.workspace
        staging_path = transaction_path / "snapshot"
        backup_path = transaction_path / "original"
        previous_state = CapturedContentState.capture(self.storage.snapshot)
        logger.info("Creating snapshot id=%s associations=%s", self.storage.snapshot.id, len(self.storage.snapshot.directories))
        try:
            self._stage_snapshot_contents(staging_path, progress_callback, message_callback)
            self._publish_created_snapshot(journal, staging_path, backup_path, had_original, replace_existing)
        except Exception as error:
            previous_state.restore_associations(self.storage.snapshot)
            previous_state.restore_capture_interval(self.storage.snapshot)
            try:
                journal.decide_rollback()
            except Exception as rollback_error:
                error.add_note(f"Persistent recovery journal retained at '{journal.path}': {rollback_error}")
            raise

        journal.finalize([backup_path], "Snapshot creation")
        logger.info("Created snapshot id=%s", self.storage.snapshot.id)

    def delete(self, message_callback=None):
        """Deletes the snapshot's directory, propagating filesystem failures.

        Args:
            message_callback (MessageCallback | None): Optional status observer receiving one message string; its
                exceptions propagate according to the calling operation.

        Returns:
            None: No return value.
        """
        recover_storage_transactions(self.storage)
        remove_directory_or_move_to_temp(self.storage.root_path(), message_callback=message_callback)

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
        recover_storage_transactions(self.storage)
        self.storage.root_path()
        if not self.storage.path_snapshot.exists():
            raise FileNotFoundError(f"The snapshot path {self.storage.path_snapshot} does not exist.")
        new_snap = self.storage.snapshot.clone()
        new_snap.id = gen_random_string(self.storage.settings.snap_id_length)
        new_snap.name = self.storage.snapshot.name + " Copy"
        new_snap.date_created = datetime.now()

        def prepare_duplicate(staging_path: Path) -> None:
            """Write and validate cloned metadata before making the duplicate visible.

            Args:
                staging_path (Path): Private tree receiving a complete copy before any final name is published.

            Returns:
                None: No return value.
            """
            json_path = staging_path / validate_directory_component(self.storage.settings.json_filename, "Snapshot JSON filename")
            self.storage.metadata.to_json(new_snap, json_path)
            validate_staged_snapshot_tree(
                staging_path,
                new_snap.id,
                self.storage.settings.json_filename,
                metadata_reader=self.storage.metadata.from_json,
            )

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

        Supply a byte-progress adapter only when the caller requested progress,
        so a create without an observer does not perform a preliminary byte scan.

        Args:
            staging_path (Path): Private tree receiving a complete copy before any final name is published.
            progress_callback (SnapshotPercentCallback | None): Optional observer receiving integer aggregate
                percentage from 0 through 100; return values do not cancel the operation.
            message_callback (MessageCallback | None): Optional status observer receiving one message string; its
                exceptions propagate according to the calling operation.

        Returns:
            None: No return value.
        """

        # We need to distribute the progress among directories if there are multiple.
        total_dirs = len(self.storage.snapshot.directories)
        for i, snap_dir in enumerate(self.storage.snapshot.directories):

            def dir_progress(copied, total):
                """Adapt copy byte counts to the current directory position.

                Args:
                    copied (int): Bytes copied for the current directory, passed to the aggregate percentage adapter.
                    total (int): Estimated total bytes for the current directory; zero-byte directories still complete.

                Returns:
                    None: No return value.
                """
                report_directory_progress(progress_callback, i, total_dirs, copied, total)

            manifest = {}
            snap_dir.copy_install_to(
                staging_path,
                progress_callback=dir_progress if progress_callback else None,
                message_callback=message_callback,
                copy_strategy=self.storage.settings.copy_strategy,
                manifest=manifest,
            )

    def _stage_snapshot_contents(self, staging_path: Path, progress_callback, message_callback) -> None:
        """Acquire every source and persist captured metadata before publishing names.

        Args:
            staging_path (Path): Private tree receiving a complete copy before any final name is published.
            progress_callback (SnapshotPercentCallback | None): Optional observer receiving integer aggregate
                percentage from 0 through 100; return values do not cancel the operation.
            message_callback (MessageCallback | None): Optional status observer receiving one message string; its
                exceptions propagate according to the calling operation.

        Returns:
            None: No return value.
        """
        self.storage.snapshot.capture_started_at = datetime.now(timezone.utc)
        self.storage.snapshot.capture_completed_at = None
        staging_path.mkdir()

        self._stage_associations(staging_path, progress_callback, message_callback)
        self.storage.snapshot.capture_completed_at = datetime.now(timezone.utc)
        if progress_callback and not self.storage.snapshot.directories:
            progress_callback(100)

        # Write json to staging BEFORE making it the final destination
        json_path = staging_path / validate_directory_component(self.storage.settings.json_filename, "Snapshot JSON filename")
        self.storage.metadata.to_json(self.storage.snapshot, json_path)

    def _publish_created_snapshot(self, journal: SnapshotTransactionJournal, staging_path: Path, backup_path: Path, had_original: bool, replace_existing: bool) -> None:
        """Recheck target presence and publish only after a durable commit decision.

        Args:
            journal (SnapshotTransactionJournal): Transaction journal owning staged paths, persisted decisions and
                cleanup.
            staging_path (Path): Private tree receiving a complete copy before any final name is published.
            backup_path (Path): Directory receiving completed backups and same-directory temporary archive files.
            had_original (bool): Whether the destination existed during planning; publication still checks concurrent
                changes.
            replace_existing (bool): Allow an existing snapshot ID to be replaced when True; otherwise collisions are
                rejected.

        Returns:
            None: No return value.

        Raises:
            FileExistsError: A destination or generated staging name already exists or changes before publication.
            FileNotFoundError: A required source, stored association or metadata entry is absent.

        Notes:
            The presence check compares whether an entry exists, not inode identity of an arbitrary replaced target.
            Journal and storage checks preserve the existing publication policy.
        """
        currently_exists = self.storage.path_snapshot.exists() or self.storage.path_snapshot.is_symlink()
        if currently_exists != had_original:
            raise FileExistsError(f"Snapshot destination '{self.storage.path_snapshot}' changed during creation.")
        if currently_exists:
            if not replace_existing:
                raise FileExistsError(f"Snapshot destination '{self.storage.path_snapshot}' already exists.")
        journal.set_state("commit_decided")
        if currently_exists:
            rename_and_sync(self.storage.path_snapshot, backup_path)
        rename_and_sync(staging_path, self.storage.path_snapshot)
        if not self.storage.path_snapshot.is_dir():
            raise FileNotFoundError(f"Published snapshot '{self.storage.path_snapshot}' is not visible after its rename.")
        journal.set_state("committed")
