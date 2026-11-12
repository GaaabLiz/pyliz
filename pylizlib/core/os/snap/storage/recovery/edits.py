"""Recover association edits without confusing overlapping old and new names."""

from __future__ import annotations

from pathlib import Path

from pylizlib.core.os.filesystem.durability import rename_and_sync
from pylizlib.core.os.filesystem.entries import entry_exists as _lexists
from pylizlib.core.os.snap.domain import validate_directory_component
from pylizlib.core.os.snap.storage.recovery.metadata import _publish_new_metadata, _restore_old_metadata, _validate_metadata_paths
from pylizlib.core.os.snap.storage.transactions import SnapshotTransactionJournal, TransactionRecoveryError


def _recover_edit(journal: SnapshotTransactionJournal, state: str, data: dict, storage) -> None:
    """Recover association renames/additions/removals from stable relative names.

    Args:
        journal (SnapshotTransactionJournal): Live journal owning the workspace, durable state and cleanup.
        state (str): Known recovery decision name; no additional transition graph is imposed.
        data (dict): Operation-specific payload, validated before destructive recovery actions.
        storage (SnapshotStorage | None): Snapshot model, layout and metadata adapter; required for operations
            using snapshot metadata.

    Returns:
        None: No return value; failure handling follows this operation's contract.

    Raises:
        TransactionRecoveryError: The journal is invalid, ambiguous or cannot be recovered safely; unresolved work
            is retained.
    """
    root = storage.path_snapshot.resolve(strict=False)
    _validate_edit(data, storage, journal.workspace)

    # Rollback parks every published target before restoring potentially overlapping old names.
    # First move published directories back to unique staging slots. Target names
    # can overlap old source names, so restoring one source at a time could
    # mistake another association for the copy being rolled back.
    if state in {"prepared", "rollback_decided"}:
        if data.get("phase") == "publishing":
            for addition in reversed(data.get("additions", [])):
                target = root / addition["target"]
                staged = journal.workspace / addition["staged"]
                if _lexists(target) and not _lexists(staged):
                    rename_and_sync(target, staged)
        for index in reversed(range(len(data.get("moves", [])))):
            move = data["moves"][index]
            staged = journal.workspace / move["staged"]
            target_name = move.get("target")
            target = root / target_name if target_name else None
            if data.get("phase") == "publishing" and target is not None and _lexists(target) and not _lexists(staged):
                rename_and_sync(target, staged)

        for index in reversed(range(len(data.get("moves", [])))):
            move = data["moves"][index]
            source = root / move["source"]
            staged = journal.workspace / move["staged"]
            if _lexists(staged) and not _lexists(source):
                rename_and_sync(staged, source)
        if state == "rollback_decided":
            _restore_old_metadata(journal, data, storage)
        journal.cleanup()
        return

    # A durable commit decision completes publications instead of restoring old names.
    if state in {"commit_decided", "committed"}:
        if state == "commit_decided":
            _complete_edit_directories(journal, data, root)
            _publish_new_metadata(journal, data, storage)
            journal.set_state("committed")
        else:
            for item in [*data.get("moves", []), *data.get("additions", [])]:
                target_name = item.get("target")
                if target_name is not None and not _lexists(root / target_name):
                    raise TransactionRecoveryError(f"Committed edit target '{target_name}' is missing.")
        journal.cleanup()


def _validate_edit(data: dict, storage, workspace: Path) -> None:
    """Constrain edit paths to single children of this snapshot and its workspace.

    Args:
        data (dict): Operation-specific payload, validated before destructive recovery actions.
        storage (SnapshotStorage | None): Snapshot model, layout and metadata adapter; required for operations
            using snapshot metadata.
        workspace (Path): Private transaction workspace containing staged metadata and relative edit names.

    Returns:
        None: No return value; failure handling follows this operation's contract.

    Raises:
        TransactionRecoveryError: The journal is invalid, ambiguous or cannot be recovered safely; unresolved work
            is retained.
    """
    moves = data.get("moves")
    additions = data.get("additions")
    if not isinstance(moves, list) or not isinstance(additions, list):
        raise TransactionRecoveryError("Edit journal moves and additions must be lists.")
    if data.get("phase") not in {"staging", "publishing"}:
        raise TransactionRecoveryError("Edit journal has an invalid phase.")
    validator = EditRecordValidator(workspace)

    for move in moves:
        validator.validate_item(move, is_addition=False)
    for addition in additions:
        validator.validate_item(addition, is_addition=True)
    _validate_metadata_paths(data, storage, workspace)


def _complete_edit_directories(journal: SnapshotTransactionJournal, data: dict, root: Path) -> None:
    """Finish all rename and addition publications after commit was decided.

    Args:
        journal (SnapshotTransactionJournal): Live journal owning the workspace, durable state and cleanup.
        data (dict): Operation-specific payload, validated before destructive recovery actions.
        root (Path): Resolved snapshot directory containing the association entries.

    Returns:
        None: No return value; failure handling follows this operation's contract.

    Raises:
        TransactionRecoveryError: The journal is invalid, ambiguous or cannot be recovered safely; unresolved work
            is retained.
    """
    for move in data.get("moves", []):
        target_name = move.get("target")
        if target_name is None:
            if not _lexists(journal.workspace / move["staged"]):
                raise TransactionRecoveryError(f"Removed directory '{move['source']}' has no recoverable copy.")
            continue
        staged = journal.workspace / move["staged"]
        target = root / target_name
        if _lexists(target):
            if _lexists(staged):
                raise TransactionRecoveryError(f"Both staged and published edit data exist for '{target}'.")
        elif _lexists(staged):
            rename_and_sync(staged, target)
        else:
            raise TransactionRecoveryError(f"Neither staged nor published edit data exists for '{target}'.")
    for addition in data.get("additions", []):
        staged = journal.workspace / addition["staged"]
        target = root / addition["target"]
        if _lexists(staged):
            if _lexists(target):
                raise TransactionRecoveryError(f"Unexpected addition destination while completing '{target}'.")
            rename_and_sync(staged, target)
        elif not _lexists(target):
            raise TransactionRecoveryError(f"Neither staged nor published addition exists for '{target}'.")


class EditRecordValidator:
    """Own duplicate-name sets for one edit plan instead of capturing mutable closures.

    Attributes:
        workspace (Path): Private transaction directory owning staged metadata and relative edit entries.
        seen_sources (set[str]): Source basenames claimed by this one edit-validation attempt.
        seen_targets (set[str]): Destination basenames claimed by this one edit-validation attempt.
        seen_staged (set[str]): Workspace staging basenames claimed by this one edit-validation attempt.

    Notes:
        Use one instance per edit plan and discard it after validation failure. Claimed-name sets can already
        contain earlier entries, preserving the original sequential validation order.
    """

    def __init__(self, workspace: Path):
        """Bind the workspace and start independent source/target/staging identity sets.

        Args:
            workspace (Path): Private transaction directory owning staged metadata and relative edit entries.

        Returns:
            None: No return value.
        """
        self.workspace = workspace
        self.seen_sources = set()
        self.seen_targets = set()
        self.seen_staged = set()

    def validate_item(self, item: dict, *, is_addition: bool) -> None:
        """Validate one persisted edit record before any recovery rename.

        Args:
            item (dict): One edit record, using relative source, target and staging basenames.
            is_addition (bool): True for an addition without a source; False for a move or removal.

        Returns:
            None: No return value; failure handling follows this operation's contract.

        Raises:
            TransactionRecoveryError: The journal is invalid, ambiguous or cannot be recovered safely; unresolved work
                is retained.
        """
        if not isinstance(item, dict):
            raise TransactionRecoveryError("Edit journal entry must be an object.")
        if not is_addition:
            source = validate_directory_component(item.get("source"), "edit transaction source")
            if source in self.seen_sources:
                raise TransactionRecoveryError("Edit journal contains duplicate source names.")
            self.seen_sources.add(source)
            if "target" not in item or (item["target"] is not None and not isinstance(item["target"], str)):
                raise TransactionRecoveryError("Edit journal move target must be a string or null.")
        elif not isinstance(item.get("target"), str):
            raise TransactionRecoveryError("Edit journal addition must have a target name.")
        if is_addition and "source" in item:
            raise TransactionRecoveryError("Edit journal addition cannot contain a source name.")
        for key in ("target",) if is_addition else ("source", "target"):
            if item.get(key) is not None:
                validate_directory_component(item[key], f"edit transaction {key}")
        if item.get("target") is not None:
            target = item["target"]
            if target in self.seen_targets:
                raise TransactionRecoveryError("Edit journal contains duplicate destination names.")
            self.seen_targets.add(target)
        staged = validate_directory_component(item.get("staged"), "edit transaction staging name")
        if staged in self.seen_staged:
            raise TransactionRecoveryError("Edit journal contains duplicate staging names.")
        self.seen_staged.add(staged)
        if (self.workspace / staged).parent.resolve(strict=False) != self.workspace.resolve(strict=False):
            raise TransactionRecoveryError("Edit staging path escaped its workspace.")
