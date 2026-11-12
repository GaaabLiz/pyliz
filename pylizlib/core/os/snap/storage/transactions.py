"""Persistent intent records and idempotent recovery for snapshot directory swaps."""

import shutil
import uuid
from pathlib import Path

from pylizlib.core.log.pylizLogger import logger
from pylizlib.core.os.filesystem.durability import rename_and_sync as rename_and_sync
from pylizlib.core.os.filesystem.durability import sync_directory as _sync_directory
from pylizlib.core.os.filesystem.entries import remove_entry as _remove_path
from pylizlib.core.os.snap.serializer import SnapshotSerializer
from pylizlib.core.os.snap.storage.recovery.models import JOURNAL_FILENAME, TRANSACTION_DIRECTORY, VALID_STATES, JournalCodec
from pylizlib.core.os.snap.storage.tree import is_link_or_junction

_VALID_STATES = VALID_STATES


class TransactionRecoveryError(RuntimeError):
    """A transaction journal is invalid or its recovery could not complete safely."""


class SnapshotTransactionJournal:
    """Persist a transaction decision before its old copies may be removed.

    Attributes:
        workspace (Path): Private transaction directory owning staged metadata and relative edit entries.
        path (Path): Native filesystem entry operated on by this method.
        payload (dict): Journal envelope or operation fields retained without schema coercion; None starts with an
            empty payload.
    """

    def __init__(self, workspace: Path, payload: dict):
        """Bind an existing transaction workspace and its in-memory journal data.

        Args:
            workspace (Path): Private transaction workspace containing staged metadata and relative edit names.
            payload (dict): Persisted envelope retained by reference, including operation data and unknown fields.

        Returns:
            None: No return value; failure handling follows this operation's contract.

        Notes:
            payload is retained by reference. Binding an existing workspace does not itself validate the envelope or
            write a journal; recovery performs validation before destructive replay.
        """
        self.workspace = Path(workspace)
        self.path = self.workspace / JOURNAL_FILENAME
        self.payload = payload

    @classmethod
    def begin(cls, scope_root: Path, operation: str, payload: dict | None = None):
        """Create and atomically publish a prepared journal in ``scope_root``.

        Args:
            scope_root (Path): Storage scope whose pending journals are scanned; normalization follows the existing
                resolved-path policy.
            operation (str): Operation discriminator; determines which path and recovery policy applies.
            payload (dict | None): Persisted envelope retained by reference, including operation data and unknown
                fields.

        Returns:
            SnapshotTransactionJournal: Prepared journal after its first atomic write; no destination has been
                modified.

        Raises:
            ValueError: A value, path, resource limit or metadata field violates the validation rules described above.

        Notes:
            A non-empty payload dictionary is retained by reference; None or an empty dictionary uses a new empty
            mapping, matching the existing truthiness rule. The v1 JSON schema and known state names are unchanged.
        """
        scope_root = Path(scope_root).resolve(strict=False)
        if not scope_root.is_dir() or is_link_or_junction(scope_root):
            raise ValueError(f"Transaction scope '{scope_root}' must be a real directory.")
        transactions_path = scope_root / TRANSACTION_DIRECTORY
        if is_link_or_junction(transactions_path):
            raise ValueError(f"Transaction directory '{transactions_path}' cannot be a link.")
        transactions_path.mkdir(exist_ok=True)
        if not _sync_directory(scope_root):
            logger.warning(f"Directory-entry durability is unavailable for transaction scope '{scope_root}'.")
        workspace = transactions_path / uuid.uuid4().hex
        workspace.mkdir()
        data = {
            "version": 1,
            "scope_root": scope_root.as_posix(),
            "operation": operation,
            "state": "prepared",
            "payload": payload or {},
        }
        journal = cls(workspace, data)
        try:
            if not _sync_directory(transactions_path):
                logger.warning(f"Directory-entry durability is unavailable for transaction directory '{transactions_path}'.")
            journal._write()
        except Exception:
            shutil.rmtree(workspace, ignore_errors=True)
            try:
                transactions_path.rmdir()
            except OSError:
                pass
            raise
        return journal

    def set_state(self, state: str) -> None:
        """Atomically persist the next recovery decision.

        Args:
            state (str): Known recovery decision name; no additional transition graph is imposed.

        Returns:
            None: No return value; failure handling follows this operation's contract.

        Raises:
            ValueError: A value, path, resource limit or metadata field violates the validation rules described above.

        Notes:
            The in-memory state changes before writing. If persistence fails, that live field still contains the
            proposed state. Known state names are validated without imposing additional transition restrictions.
        """
        if state not in _VALID_STATES:
            raise ValueError(f"Unknown transaction state: {state!r}.")
        self.payload["state"] = state
        self._write()
        logger.debug("Snapshot journal=%s decision=%s", self.workspace.name, state)

    def finalize(self, cleanup_paths=(), operation: str = "Snapshot operation") -> bool:
        """Remove committed leftovers and keep the journal if any removal fails.

        Args:
            cleanup_paths (Iterable[Path]): Committed backup/staging paths to remove before deleting the journal.
            operation (str): Operation discriminator; determines which path and recovery policy applies.

        Returns:
            bool: True when cleanup completes; False when a cleanup error is logged and the journal is retained.

        Notes:
            Cleanup is best effort and may already have removed part of a backup before failure. Never use cleanup
            leftovers as an unconditional rollback source after commit.

            False can mean cleanup partially succeeded before failing. A missing subset of backup entries must not
            trigger a new rollback after the content commit.
        """
        failed = False
        for path in cleanup_paths:
            try:
                _remove_path(Path(path))
            except OSError as error:
                failed = True
                logger.warning(f"{operation} committed, but could not remove '{path}': {error}")
        if failed:
            return False
        try:
            self.cleanup()
        except OSError as error:
            logger.warning(f"{operation} committed, but journal cleanup failed at '{self.workspace}': {error}")
            return False
        try:
            self.workspace.parent.rmdir()
        except OSError:
            pass
        return True

    def update_payload(self, **values) -> None:
        """Persist additional staged paths or plan entries before publication.

        Args:
            **values (object): Payload fields to merge in place and persist without changing unrelated fields.

        Returns:
            None: No return value; failure handling follows this operation's contract.
        """
        self.payload["payload"].update(values)
        self._write()

    def cleanup(self) -> None:
        """Remove a resolved transaction workspace and its journal sidecars.

        Returns:
            None: No return value; failure handling follows this operation's contract.
        """
        _remove_path(self.workspace)
        try:
            self.workspace.parent.rmdir()
        except OSError:
            pass

    def recover(self, storage=None) -> None:
        """Run the same idempotent recovery used after a process restart.

        Args:
            storage (SnapshotStorage | None): Snapshot model, layout and metadata adapter; required for operations
                using snapshot metadata.

        Returns:
            None: No return value; failure handling follows this operation's contract.
        """
        from pylizlib.core.os.snap.storage.recovery.coordinator import _recover_one

        _recover_one(self, storage)

    def decide_rollback(self, storage=None) -> None:
        """Persist rollback intent before restoring entries and removing staging.

        Args:
            storage (SnapshotStorage | None): Snapshot model, layout and metadata adapter; required for operations
                using snapshot metadata.

        Returns:
            None: No return value; failure handling follows this operation's contract.
        """
        self.set_state("rollback_decided")
        self.recover(storage)

    def _write(self) -> None:
        """Encode and atomically replace this journal file.

        Returns:
            None: No return value; failure handling follows this operation's contract.
        """
        SnapshotSerializer.write_text(self.path, JournalCodec.encode(self.payload))


def recover_pending_transactions(scope_root: Path, storage=None) -> list[str]:
    """Compatibility entry point; see recovery.coordinator.recover_pending_transactions for its contract.

    Args:
        scope_root (Path): Storage scope whose pending journals are scanned; normalization follows the existing
            resolved-path policy.
        storage (SnapshotStorage | None): Snapshot model, layout and metadata adapter; required for operations
            using snapshot metadata.

    Returns:
        list[str]: Recovered operation names in workspace order; empty when no journal needed recovery. Recovery
            may rename/delete entries and refresh the live model.
    """
    from pylizlib.core.os.snap.storage.recovery.coordinator import recover_pending_transactions as implementation

    return implementation(scope_root, storage)


def recover_storage_transactions(storage) -> list[str]:
    """Compatibility entry point; see recovery.coordinator.recover_storage_transactions for its contract.

    Args:
        storage (SnapshotStorage | None): Snapshot model, layout and metadata adapter; required for operations
            using snapshot metadata.

    Returns:
        list[str]: Operation names recovered first from catalogue scope, then snapshot scope.
    """
    from pylizlib.core.os.snap.storage.recovery.coordinator import recover_storage_transactions as implementation

    return implementation(storage)


def prepare_snapshot_metadata(storage, workspace: Path, *, field_name: str | None = None, field_value=None) -> dict:
    """Compatibility entry point; see recovery.metadata.prepare_snapshot_metadata for its contract.

    Args:
        storage (SnapshotStorage | None): Snapshot model, layout and metadata adapter; required for operations
            using snapshot metadata.
        workspace (Path): Private transaction workspace containing staged metadata and relative edit names.
        field_name (str | None): Single metadata field to patch, or None to serialize the complete live model.
        field_value (object): Value for the requested partial metadata update; ignored for a complete model save.

    Returns:
        dict: Workspace-relative old/new filenames and the active metadata basename under keys old, new and
            target.
    """
    from pylizlib.core.os.snap.storage.recovery.metadata import prepare_snapshot_metadata as implementation

    return implementation(storage, workspace, field_name=field_name, field_value=field_value)
