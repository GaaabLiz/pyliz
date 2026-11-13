"""Durable, resumable rollback of edits whose old and new names may overlap."""

from __future__ import annotations

from pathlib import Path

from pylizlib.core.os.filesystem.durability import rename_and_sync
from pylizlib.core.os.filesystem.entries import entry_exists
from pylizlib.core.os.filesystem.tree import is_link_or_junction
from pylizlib.core.os.snap.storage.recovery.metadata import _restore_old_metadata
from pylizlib.core.os.snap.storage.transactions import SnapshotTransactionJournal, TransactionRecoveryError

EDIT_ROLLBACK_PHASES = {"not_started", "parking", "restoring", "restored"}


class EditRollback:
    """Keep rollback progress durable before restoring names or deleting staging.

    Attributes:
        journal (SnapshotTransactionJournal): Workspace and persisted edit intent, upgraded to v2 before rollback.
        storage (SnapshotStorage): Live snapshot model and its protected metadata adapter.
        data (dict): Operation payload retained by reference, including original phase and rollback progress.
        root (Path): Resolved stored snapshot directory containing old and published association names.
    """

    def __init__(self, journal: SnapshotTransactionJournal, storage):
        """Bind one validated edit journal and its current snapshot context.

        Args:
            journal (SnapshotTransactionJournal): Validated prepared or rollback-decided edit journal.
            storage (SnapshotStorage): Snapshot context used to restore old JSON and directory names.

        Returns:
            None: Construction performs no writes or directory moves.
        """
        self.journal = journal
        self.storage = storage
        self.data = journal.payload["payload"]
        self.root = storage.path_snapshot.resolve(strict=False)

    def run(self) -> None:
        """Park new targets, restore originals, persist completion, then clean up.

        Returns:
            None: Every original name and required old metadata is restored before disposable staging is removed.

        Raises:
            TransactionRecoveryError: Legacy progress or entry identity is ambiguous; every remaining copy and
                journal is retained.
            OSError: Persistence, rename or cleanup fails; the recorded phase permits another recovery attempt.
        """
        phase = self.data.get("rollback_phase")
        if phase is None:
            self._check_legacy_progress()
            phase = "not_started"

        # Re-persist even an existing marker: a previous failed write may have changed this live object only.
        self.journal.payload["version"] = 2
        self.journal.update_payload(rollback_phase=phase)
        if phase == "not_started":
            self.journal.update_payload(rollback_phase="parking")
            phase = "parking"
        if phase == "parking":
            self._park_published_targets()

            # No old name is restored until every published target has been parked durably.
            self.journal.update_payload(rollback_phase="restoring")
            phase = "restoring"
        if phase == "restoring":
            self._restore_originals()
            if self.journal.payload["state"] == "rollback_decided":
                _restore_old_metadata(self.journal, self.data, self.storage)

            # Cleanup may remove metadata copies and additions; later replay must never park old sources again.
            self.journal.update_payload(rollback_phase="restored")
        self._assert_originals_present()
        self.journal.cleanup()

    def _check_legacy_progress(self) -> None:
        """Stop rather than guess when an older overlapping rollback may already have restored names.

        Returns:
            None: Legacy names are disjoint, original staging has not been consumed, or publication never started.

        Raises:
            TransactionRecoveryError: Overlapping publishing names lack enough durable progress information.
        """
        if self.data["phase"] != "publishing":
            return
        sources = {Path(move["source"]) for move in self.data["moves"]}
        reused = any(move["target"] is not None and Path(move["target"]) in sources and move["target"] != move["source"] for move in self.data["moves"])
        reused = reused or any(Path(addition["target"]) in sources for addition in self.data["additions"])
        all_originals_staged = all(entry_exists(self.journal.workspace / move["staged"]) for move in self.data["moves"])
        if reused and not all_originals_staged:
            raise TransactionRecoveryError("Legacy overlapping edit journal has ambiguous rollback progress; journal and all remaining copies were retained.")

    def _park_published_targets(self) -> None:
        """Move every published target back to its unique slot before restoring any original name.

        Returns:
            None: Published targets are parked, or the original edit never left its staging phase.

        Raises:
            TransactionRecoveryError: Both the target and its private slot exist, so their ownership is ambiguous.
            OSError: A rename or parent-directory flush fails.
        """
        if self.data["phase"] != "publishing":
            return
        entries = [*reversed(self.data["additions"]), *reversed(self.data["moves"])]
        for item in entries:
            target_name = item.get("target")
            if target_name is None:
                continue
            target = self.root / target_name
            staged = self.journal.workspace / item["staged"]
            if entry_exists(target):
                if entry_exists(staged):
                    raise TransactionRecoveryError(f"Both staged and published rollback copies exist for '{target}'.")
                rename_and_sync(target, staged)

    def _restore_originals(self) -> None:
        """Restore or recognize each original, refusing to discard conflicting copies.

        Returns:
            None: Every original is restored or was already restored by an earlier recovery attempt.

        Raises:
            TransactionRecoveryError: Both copies or neither copy exist for an original name.
            OSError: A rename or parent-directory flush fails.
        """
        for item in self.data["moves"]:
            source = self.root / item["source"]
            staged = self.journal.workspace / item["staged"]
            if entry_exists(source) == entry_exists(staged):
                raise TransactionRecoveryError(f"Cannot determine the original rollback copy for '{source}'; remaining data was retained.")
        for item in reversed(self.data["moves"]):
            source = self.root / item["source"]
            staged = self.journal.workspace / item["staged"]
            if entry_exists(staged):
                if entry_exists(source):
                    raise TransactionRecoveryError(f"Rollback source '{source}' appeared before restoration.")
                rename_and_sync(staged, source)

    def _assert_originals_present(self) -> None:
        """Require every restored old association before removing its recovery workspace.

        Returns:
            None: All old association roots are real directories.

        Raises:
            TransactionRecoveryError: A restored source is absent, linked or no longer a real directory.
        """
        for move in self.data["moves"]:
            source = self.root / move["source"]
            if not source.is_dir() or is_link_or_junction(source):
                raise TransactionRecoveryError(f"Restored original '{source}' is not a real directory; recovery workspace was retained.")
