"""Scan pending journals and dispatch validated recovery to the matching handler."""

import json
from pathlib import Path

from pylizlib.core.log.pylizLogger import logger
from pylizlib.core.os.filesystem.entries import remove_entry as _remove_path
from pylizlib.core.os.snap.serializer import SnapshotSerializer
from pylizlib.core.os.snap.storage.recovery.edits import _recover_edit
from pylizlib.core.os.snap.storage.recovery.metadata import _refresh_snapshot_model
from pylizlib.core.os.snap.storage.recovery.models import JOURNAL_FILENAME, TRANSACTION_DIRECTORY, JournalCodec
from pylizlib.core.os.snap.storage.recovery.replacements import (
    recover_manifest_restore,
    recover_replacements,
)
from pylizlib.core.os.snap.storage.recovery.tree import _recover_snapshot_tree
from pylizlib.core.os.snap.storage.transactions import SnapshotTransactionJournal, TransactionRecoveryError
from pylizlib.core.os.snap.storage.tree import is_link_or_junction


def recover_pending_transactions(scope_root: Path, storage=None) -> list[str]:
    """Recover every journal in one storage scope before new work begins.

    A ``prepared`` transaction rolls back; a ``commit_decided`` transaction
    finishes publishing its staged metadata; ``committed`` only needs cleanup.
    Journals that cannot be validated or recovered are left in place and raised
    so callers never proceed over an ambiguous tree.

    Args:
        scope_root (Path): Storage scope whose pending journals are scanned; normalization follows the existing
            resolved-path policy.
        storage (SnapshotStorage | None): Snapshot model, layout and metadata adapter; required for operations
            using snapshot metadata.

    Returns:
        list[str]: Recovered operation names in workspace order; empty when no journal needed recovery. Recovery
            may rename/delete entries and refresh the live model.

    Raises:
        TransactionRecoveryError: The journal is invalid, ambiguous or cannot be recovered safely; unresolved work
            is retained.
    """
    scope_root = Path(scope_root).resolve(strict=False)
    transactions_path = scope_root / TRANSACTION_DIRECTORY
    if is_link_or_junction(transactions_path):
        raise TransactionRecoveryError(f"Transaction directory '{transactions_path}' cannot be a link.")
    if not transactions_path.exists():
        return []
    recovered = []

    # Visit journals deterministically; an ambiguous workspace blocks new operations.
    for workspace in sorted(transactions_path.iterdir()):
        if is_link_or_junction(workspace) or not workspace.is_dir():
            raise TransactionRecoveryError(f"Unexpected entry in transaction directory: '{workspace}'.")
        journal_path = workspace / JOURNAL_FILENAME

        # The process could stop after creating an empty workspace but before
        # publishing its journal. No destructive operation starts before it.
        if not journal_path.exists():
            _remove_path(workspace)
            continue

        # Validate the envelope before handing any destructive work to an operation handler.
        try:
            payload = json.loads(SnapshotSerializer.read_text(journal_path))
            JournalCodec.validate(payload, scope_root)
            journal = SnapshotTransactionJournal(workspace, payload)
            logger.info("Recovering snapshot operation=%s journal=%s state=%s", payload["operation"], workspace.name, payload["state"])
            _recover_one(journal, storage)
            logger.info("Recovered snapshot operation=%s journal=%s", payload["operation"], workspace.name)
        except Exception as error:
            if isinstance(error, TransactionRecoveryError):
                raise
            raise TransactionRecoveryError(f"Could not recover transaction '{workspace}': {error}") from error
        recovered.append(str(payload["operation"]))
    try:
        transactions_path.rmdir()

    # Another transaction may have started after the scan. Its own journal
    # remains authoritative; leaving the shared parent is harmless.
    except OSError:
        pass

    # Refresh the caller-owned model only after all selected recovery work completes.
    if recovered and storage is not None and storage.path_snapshot_json.is_file():
        _refresh_snapshot_model(storage)
    return recovered


def recover_storage_transactions(storage) -> list[str]:
    """Recover catalogue-root and snapshot-root journals before a new operation.

    Args:
        storage (SnapshotStorage | None): Snapshot model, layout and metadata adapter; required for operations
            using snapshot metadata.

    Returns:
        list[str]: Operation names recovered first from catalogue scope, then snapshot scope.
    """
    recovered = recover_pending_transactions(storage.path_catalogue, storage)
    if storage.path_snapshot.is_dir():
        recovered.extend(recover_pending_transactions(storage.path_snapshot, storage))
    return recovered


def _recover_one(journal: SnapshotTransactionJournal, storage) -> None:
    """Dispatch one journal to rollback, commit completion or cleanup.

    Args:
        journal (SnapshotTransactionJournal): Live journal owning the workspace, durable state and cleanup.
        storage (SnapshotStorage | None): Snapshot model, layout and metadata adapter; required for operations
            using snapshot metadata.

    Returns:
        None: No return value; failure handling follows this operation's contract.

    Raises:
        TransactionRecoveryError: The journal is invalid, ambiguous or cannot be recovered safely; unresolved work
            is retained.
    """
    operation = journal.payload["operation"]
    state = journal.payload["state"]
    data = journal.payload["payload"]
    if operation == "snapshot_tree":
        _recover_snapshot_tree(journal, state, data)
        return
    if operation == "restore_associations_manifest":
        recover_manifest_restore(journal, state, data)
        return
    if storage is None:
        raise TransactionRecoveryError(f"Transaction '{operation}' requires snapshot metadata context.")
    if operation == "edit":
        _recover_edit(journal, state, data, storage)
        return
    if operation not in {"install", "sync", "restore_associations"}:
        raise TransactionRecoveryError(f"Unknown snapshot transaction type: {operation!r}.")
    recover_replacements(journal, state, data, storage, operation)
