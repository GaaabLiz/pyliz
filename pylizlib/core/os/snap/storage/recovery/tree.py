"""Recover publication of a complete snapshot tree."""

from __future__ import annotations

from pathlib import Path

from pylizlib.core.os.filesystem.durability import rename_and_sync
from pylizlib.core.os.filesystem.entries import entry_exists as _lexists
from pylizlib.core.os.filesystem.entries import remove_entry as _remove_path
from pylizlib.core.os.snap.domain import validate_directory_component
from pylizlib.core.os.snap.storage.transactions import SnapshotTransactionJournal, TransactionRecoveryError


def _recover_snapshot_tree(journal: SnapshotTransactionJournal, state: str, data: dict) -> None:
    """Finish or undo a whole-snapshot publication using its private staging tree.

    Args:
        journal (SnapshotTransactionJournal): Live journal owning the workspace, durable state and cleanup.
        state (str): Known recovery decision name; no additional transition graph is imposed.
        data (dict): Operation-specific payload, validated before destructive recovery actions.


    Returns:
        None: After the requested validation, persistence or recovery phase completes; failures propagate unless explicitly handled above.
    """
    scope_root = Path(journal.payload["scope_root"])
    snapshot_id = validate_directory_component(data.get("snapshot_id"), "transaction snapshot ID")
    if type(data.get("had_original")) is not bool:
        raise TransactionRecoveryError("Snapshot-tree journal 'had_original' must be a boolean.")
    destination = scope_root / snapshot_id
    staged = journal.workspace / "snapshot"
    backup = journal.workspace / "original"
    if state in {"prepared", "rollback_decided"}:
        if _lexists(backup):
            if _lexists(destination):
                _remove_path(destination)
            rename_and_sync(backup, destination)
        elif not data.get("had_original") and not _lexists(staged) and _lexists(destination):
            _remove_path(destination)
        _remove_path(staged)
        journal.cleanup()
        return
    if state == "commit_decided":
        if _lexists(staged):
            if _lexists(destination):
                if data.get("had_original") and not _lexists(backup):
                    rename_and_sync(destination, backup)
                else:
                    raise TransactionRecoveryError(f"Unexpected snapshot destination '{destination}'.")
            rename_and_sync(staged, destination)
        elif not _lexists(destination):
            raise TransactionRecoveryError(f"Neither staged nor published snapshot exists for '{destination}'.")
        journal.set_state("committed")
    if journal.payload["state"] == "committed":
        if not _lexists(destination):
            raise TransactionRecoveryError(f"Committed snapshot destination '{destination}' is missing; original data was preserved.")
        journal.cleanup()
