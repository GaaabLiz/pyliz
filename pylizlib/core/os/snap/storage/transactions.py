"""Persistent intent records and idempotent recovery for snapshot directory swaps."""

import json
import os
import shutil
import uuid
from copy import deepcopy
from dataclasses import fields
from pathlib import Path

from pylizlib.core.log.pylizLogger import logger
from pylizlib.core.os.filesystem.durability import rename_and_sync as rename_and_sync
from pylizlib.core.os.filesystem.durability import sync_directory as _sync_directory
from pylizlib.core.os.filesystem.entries import entry_exists as _lexists
from pylizlib.core.os.filesystem.entries import remove_entry as _remove_path
from pylizlib.core.os.snap.domain import SnapDirAssociation, Snapshot, validate_directory_component
from pylizlib.core.os.snap.serializer import SnapshotSerializer
from pylizlib.core.os.snap.storage.tree import is_link_or_junction

TRANSACTION_DIRECTORY = ".pyliz_transactions"
JOURNAL_FILENAME = "journal.json"
_VALID_STATES = {"prepared", "rollback_decided", "commit_decided", "committed"}


class TransactionRecoveryError(RuntimeError):
    """A transaction journal is invalid or its recovery could not complete safely."""


class SnapshotTransactionJournal:
    """Persist a transaction decision before its old copies may be removed."""

    def __init__(self, workspace: Path, payload: dict):
        """Bind an existing transaction workspace and its in-memory journal data."""
        self.workspace = Path(workspace)
        self.path = self.workspace / JOURNAL_FILENAME
        self.payload = payload

    @classmethod
    def begin(cls, scope_root: Path, operation: str, payload: dict | None = None):
        """Create and atomically publish a prepared journal in ``scope_root``."""
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
        """Atomically persist the next recovery decision."""
        if state not in _VALID_STATES:
            raise ValueError(f"Unknown transaction state: {state!r}.")
        self.payload["state"] = state
        self._write()

    def finalize(self, cleanup_paths=(), operation: str = "Snapshot operation") -> bool:
        """Remove committed leftovers and keep the journal if any removal fails."""
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
        """Persist additional staged paths or plan entries before publication."""
        self.payload["payload"].update(values)
        self._write()

    def cleanup(self) -> None:
        """Remove a resolved transaction workspace and its journal sidecars."""
        _remove_path(self.workspace)
        try:
            self.workspace.parent.rmdir()
        except OSError:
            pass

    def recover(self, storage=None) -> None:
        """Run the same idempotent recovery used after a process restart."""
        _recover_one(self, storage)

    def decide_rollback(self, storage=None) -> None:
        """Persist rollback intent before restoring entries and removing staging."""
        self.set_state("rollback_decided")
        self.recover(storage)

    def _write(self) -> None:
        """Encode and atomically replace this journal file."""
        SnapshotSerializer.write_text(self.path, json.dumps(self.payload, indent=2))


def recover_pending_transactions(scope_root: Path, storage=None) -> list[str]:
    """Recover every journal in one storage scope before new work begins.

    A ``prepared`` transaction rolls back; a ``commit_decided`` transaction
    finishes publishing its staged metadata; ``committed`` only needs cleanup.
    Journals that cannot be validated or recovered are left in place and raised
    so callers never proceed over an ambiguous tree.
    """
    scope_root = Path(scope_root).resolve(strict=False)
    transactions_path = scope_root / TRANSACTION_DIRECTORY
    if is_link_or_junction(transactions_path):
        raise TransactionRecoveryError(f"Transaction directory '{transactions_path}' cannot be a link.")
    if not transactions_path.exists():
        return []
    recovered = []
    for workspace in sorted(transactions_path.iterdir()):
        if is_link_or_junction(workspace) or not workspace.is_dir():
            raise TransactionRecoveryError(f"Unexpected entry in transaction directory: '{workspace}'.")
        journal_path = workspace / JOURNAL_FILENAME
        if not journal_path.exists():
            # The process could stop after creating an empty workspace but before
            # publishing its journal. No destructive operation starts before it.
            _remove_path(workspace)
            continue
        try:
            payload = json.loads(SnapshotSerializer.read_text(journal_path))
            _validate_journal(payload, scope_root)
            journal = SnapshotTransactionJournal(workspace, payload)
            _recover_one(journal, storage)
        except Exception as error:
            if isinstance(error, TransactionRecoveryError):
                raise
            raise TransactionRecoveryError(f"Could not recover transaction '{workspace}': {error}") from error
        recovered.append(str(payload["operation"]))
    try:
        transactions_path.rmdir()
    except OSError:
        # Another transaction may have started after the scan. Its own journal
        # remains authoritative; leaving the shared parent is harmless.
        pass
    if recovered and storage is not None and storage.path_snapshot_json.is_file():
        _refresh_snapshot_model(storage)
    return recovered


def recover_storage_transactions(storage) -> list[str]:
    """Recover catalogue-root and snapshot-root journals before a new operation."""
    recovered = recover_pending_transactions(storage.path_catalogue, storage)
    if storage.path_snapshot.is_dir():
        recovered.extend(recover_pending_transactions(storage.path_snapshot, storage))
    return recovered


def prepare_snapshot_metadata(storage, workspace: Path, *, field_name: str | None = None, field_value=None) -> dict:
    """Save exact old and proposed JSON bytes inside a transaction workspace."""
    workspace = Path(workspace)
    old_path = workspace / "metadata-old.json"
    new_path = workspace / "metadata-new.json"
    old_bytes = storage.metadata.read_bytes(storage.path_snapshot_json)
    storage.metadata.write_bytes(old_path, old_bytes)
    if field_name is None:
        storage.metadata.to_json(storage.snapshot, new_path)
    else:
        storage.metadata.write_bytes(new_path, old_bytes)
        storage.metadata.update_field(new_path, field_name, field_value)
    return {"old": old_path.name, "new": new_path.name, "target": storage.path_snapshot_json.name}


def _validate_journal(payload: dict, scope_root: Path) -> None:
    """Reject malformed journals and entries that refer to another storage root."""
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise TransactionRecoveryError("Unsupported snapshot transaction journal version.")
    if payload.get("scope_root") != scope_root.as_posix():
        raise TransactionRecoveryError("Transaction journal belongs to another storage scope.")
    if not isinstance(payload.get("operation"), str):
        raise TransactionRecoveryError("Transaction journal operation must be a string.")
    if payload.get("state") not in _VALID_STATES:
        raise TransactionRecoveryError("Transaction journal has an invalid state.")
    if not isinstance(payload.get("payload"), dict):
        raise TransactionRecoveryError("Transaction journal payload must be an object.")


def _recover_one(journal: SnapshotTransactionJournal, storage) -> None:
    """Dispatch one journal to rollback, commit completion or cleanup."""
    operation = journal.payload["operation"]
    state = journal.payload["state"]
    data = journal.payload["payload"]
    if operation == "snapshot_tree":
        _recover_snapshot_tree(journal, state, data)
        return
    if operation == "restore_associations_manifest":
        _validate_manifest_restore_entries(data, journal.workspace)
        if state in {"prepared", "rollback_decided"}:
            _rollback_replacements(data)
            journal.cleanup()
            return
        if state in {"commit_decided", "committed"}:
            _complete_replacements(data)
            if state == "commit_decided":
                journal.set_state("committed")
            _cleanup_replacements(data)
            journal.cleanup()
            return
        raise TransactionRecoveryError("Manifest restore journal has an unsupported state.")
    if storage is None:
        raise TransactionRecoveryError(f"Transaction '{operation}' requires snapshot metadata context.")
    if operation == "edit":
        _recover_edit(journal, state, data, storage)
        return
    if operation not in {"install", "sync", "restore_associations"}:
        raise TransactionRecoveryError(f"Unknown snapshot transaction type: {operation!r}.")
    _validate_replacement_entries(operation, data, storage, journal.workspace)
    if state in {"prepared", "rollback_decided"}:
        _rollback_replacements(data)
        if state == "rollback_decided" and data.get("metadata"):
            _restore_old_metadata(journal, data, storage)
        journal.cleanup()
        return
    if state in {"commit_decided", "committed"}:
        _complete_replacements(data)
        if state == "commit_decided":
            _publish_new_metadata(journal, data, storage)
            journal.set_state("committed")
        _cleanup_replacements(data)
        journal.cleanup()


def _validate_manifest_restore_entries(data: dict, workspace: Path) -> None:
    """Validate self-contained AD restore records before replaying their swaps."""
    entries = data.get("entries")
    if not isinstance(entries, list):
        raise TransactionRecoveryError("Manifest restore journal has no entry list.")
    workspace = workspace.resolve(strict=False)
    scope_root = workspace.parent.parent.resolve(strict=False)
    transaction_root = workspace.parent.resolve(strict=False)
    seen_ids = set()
    destinations = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise TransactionRecoveryError("Manifest restore journal entry must be an object.")
        folder_id = entry.get("folder_id")
        if not isinstance(folder_id, str) or not folder_id or folder_id in seen_ids:
            raise TransactionRecoveryError("Manifest restore journal has an invalid or duplicate association ID.")
        seen_ids.add(folder_id)
        for key in ("stage", "destination", "backup"):
            if not isinstance(entry.get(key), str) or not entry[key]:
                raise TransactionRecoveryError(f"Manifest restore journal path '{key}' must be a nonempty string.")
        if type(entry.get("had_original")) is not bool:
            raise TransactionRecoveryError("Manifest restore journal 'had_original' must be a boolean.")
        stage = Path(entry["stage"])
        destination = Path(entry["destination"])
        backup = Path(entry["backup"])
        if not stage.is_absolute() or not destination.is_absolute() or not backup.is_absolute():
            raise TransactionRecoveryError("Manifest restore journal paths must be absolute.")
        if stage.parent.resolve(strict=False) != destination.parent.resolve(strict=False):
            raise TransactionRecoveryError("Manifest restore staging path must be beside its destination.")
        if is_link_or_junction(stage) or not stage.name.startswith(f"{destination.name}_staging_"):
            raise TransactionRecoveryError("Manifest restore staging path is not a generated destination sibling.")
        if backup.parent != destination.parent or not backup.name.startswith(f"{destination.name}_bck_"):
            raise TransactionRecoveryError("Manifest restore backup is not a generated sibling of its destination.")
        resolved_destination = destination.resolve(strict=False)
        if resolved_destination == scope_root or scope_root in resolved_destination.parents:
            raise TransactionRecoveryError("Manifest restore destination overlaps catalogue transaction storage.")
        if resolved_destination == transaction_root or transaction_root in resolved_destination.parents:
            raise TransactionRecoveryError("Manifest restore destination overlaps its transaction workspace.")
        destinations.append((folder_id, resolved_destination))

    for index, (folder_id, destination) in enumerate(destinations):
        for other_id, other_destination in destinations[index + 1 :]:
            if destination == other_destination or destination in other_destination.parents or other_destination in destination.parents:
                raise TransactionRecoveryError(f"Manifest restore destinations '{folder_id}' and '{other_id}' overlap or are nested.")


def _validate_replacement_entries(operation: str, data: dict, storage, workspace: Path) -> None:
    """Constrain journal swaps to the current snapshot and its live associations."""
    if not isinstance(data.get("entries"), list):
        raise TransactionRecoveryError("Replacement journal has no entry list.")
    associations = {association.folder_id: association for association in storage.snapshot.directories}
    root = storage.path_snapshot.resolve(strict=False)
    for entry in data["entries"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("folder_id"), str):
            raise TransactionRecoveryError("Replacement journal entry has no association identity.")
        association = associations.get(entry["folder_id"])
        if association is None:
            # A commit-decided edit does not use this handler; other replacement
            # operations must still match the persisted association set.
            raise TransactionRecoveryError(f"Unknown association in transaction: {entry['folder_id']!r}.")
        for key in ("stage", "destination", "backup"):
            if not isinstance(entry.get(key), str) or not entry[key]:
                raise TransactionRecoveryError(f"Replacement journal path '{key}' must be a nonempty string.")
        if type(entry.get("had_original")) is not bool:
            raise TransactionRecoveryError("Replacement journal 'had_original' must be a boolean.")
        if entry.get("merge_child", False) and operation != "install":
            raise TransactionRecoveryError("Only install journals may contain merge entries.")
        if "stage_root" in entry and not isinstance(entry["stage_root"], str):
            raise TransactionRecoveryError("Replacement journal stage root must be a string.")
        stage = Path(entry["stage"])
        destination = Path(entry["destination"])
        backup = Path(entry["backup"])
        if operation in {"install", "restore_associations"}:
            live = Path(os.path.abspath(association.original_path))
            if operation == "install" and entry.get("merge_child"):
                if destination.parent != live or stage.parent != Path(entry.get("stage_root", stage.parent)):
                    raise TransactionRecoveryError("Install merge journal escaped its associated directory.")
            elif destination != live:
                raise TransactionRecoveryError("Transaction destination does not match its association.")
            if backup.parent != destination.parent or not backup.name.startswith(f"{destination.name}_bck_"):
                raise TransactionRecoveryError("External backup path is not a generated sibling of its destination.")
            stage_root = Path(entry.get("stage_root", stage.parent))
            if operation == "restore_associations":
                if not stage.resolve(strict=False).is_relative_to(workspace.resolve(strict=False)):
                    raise TransactionRecoveryError("Restore staging path escaped its transaction workspace.")
            else:
                if stage_root.parent != destination.parent or not stage_root.name.startswith(f"{live.name}_staging_"):
                    raise TransactionRecoveryError("Install staging path is not a generated sibling of its destination.")
                if not entry.get("merge_child") and stage != stage_root:
                    raise TransactionRecoveryError("Install staging directory does not match its journal entry.")
        elif operation == "sync":
            expected = root / association.directory_name
            if destination != expected or stage.parent != root or backup.parent != root:
                raise TransactionRecoveryError("Sync transaction paths must be direct children of the snapshot root.")
            if not stage.name.startswith(f"{expected.name}_staging_") or not backup.name.startswith(f"{expected.name}_bck_"):
                raise TransactionRecoveryError("Sync transaction uses an unexpected staging or backup name.")
        for path in (stage, destination, backup):
            if path.name in {"", ".", ".."}:
                raise TransactionRecoveryError("Transaction journal contains an invalid path.")
    staging_roots = data.get("staging_roots", [])
    if not isinstance(staging_roots, list):
        raise TransactionRecoveryError("Replacement journal staging roots must be a list.")
    for raw_path in staging_roots:
        if not isinstance(raw_path, str) or not raw_path:
            raise TransactionRecoveryError("Replacement journal staging root must be a nonempty string.")
        path = Path(raw_path)
        if operation == "sync":
            allowed = path.parent == root and any(path.name.startswith(f"{association.directory_name}_staging_") for association in associations.values())
        elif operation == "install":
            allowed = any(
                path.parent == live.parent and path.name.startswith(f"{live.name}_staging_") for live in (Path(os.path.abspath(association.original_path)) for association in associations.values())
            )
        else:
            allowed = False
        if not allowed:
            raise TransactionRecoveryError("Replacement journal staging root is outside its generated staging paths.")
    _validate_metadata_paths(data, storage, workspace)


def _validate_metadata_paths(data: dict, storage, workspace: Path) -> None:
    """Ensure staged metadata and active JSON both belong to this snapshot."""
    metadata = data.get("metadata")
    if metadata is None:
        return
    if not isinstance(metadata, dict) or metadata.get("target") != storage.path_snapshot_json.name:
        raise TransactionRecoveryError("Transaction metadata target does not match the snapshot JSON file.")
    for key in ("old", "new"):
        name = validate_directory_component(metadata.get(key), "transaction metadata filename")
        path = workspace / name
        if path.parent.resolve(strict=False) != workspace.resolve(strict=False):
            raise TransactionRecoveryError("Transaction metadata file escaped its workspace.")


def _rollback_replacements(data: dict) -> None:
    """Restore replaced originals and remove copies that had no prior target."""
    for entry in reversed(data.get("entries", [])):
        stage = Path(entry["stage"])
        destination = Path(entry["destination"])
        backup = Path(entry["backup"])
        if _lexists(backup):
            if _lexists(destination):
                _remove_path(destination)
            rename_and_sync(backup, destination)
        elif not entry["had_original"] and not _lexists(stage) and _lexists(destination):
            _remove_path(destination)
        if _lexists(stage):
            _remove_path(stage)
    for path in data.get("staging_roots", []):
        _remove_path(Path(path))


def _complete_replacements(data: dict) -> None:
    """Finish directory swaps after the durable commit decision was written."""
    for entry in data.get("entries", []):
        stage = Path(entry["stage"])
        destination = Path(entry["destination"])
        backup = Path(entry["backup"])
        if _lexists(stage):
            if _lexists(destination):
                if entry["had_original"] and not _lexists(backup):
                    rename_and_sync(destination, backup)
                else:
                    raise TransactionRecoveryError(f"Unexpected destination while completing '{destination}'.")
            rename_and_sync(stage, destination)
        elif not _lexists(destination):
            raise TransactionRecoveryError(f"Neither staging nor published data exists for '{destination}'.")


def _cleanup_replacements(data: dict) -> None:
    """Delete backups and staging only after the journal records committed state."""
    for entry in data.get("entries", []):
        _remove_path(Path(entry["backup"]))
        _remove_path(Path(entry["stage"]))
    for path in data.get("staging_roots", []):
        _remove_path(Path(path))


def _publish_new_metadata(journal: SnapshotTransactionJournal, data: dict, storage) -> None:
    """Publish the prepared JSON after all new directory entries are available."""
    metadata = data.get("metadata")
    if metadata is None:
        return
    new_bytes = storage.metadata.read_bytes(journal.workspace / metadata["new"])
    storage.metadata.write_bytes(storage.path_snapshot_json, new_bytes)


def _restore_old_metadata(journal: SnapshotTransactionJournal, data: dict, storage) -> None:
    """Restore exact old metadata bytes while recovering a decided rollback."""
    metadata = data.get("metadata")
    if metadata is None:
        return
    old_bytes = storage.metadata.read_bytes(journal.workspace / metadata["old"])
    if storage.metadata.read_bytes(storage.path_snapshot_json) != old_bytes:
        storage.metadata.write_bytes(storage.path_snapshot_json, old_bytes)


def _recover_edit(journal: SnapshotTransactionJournal, state: str, data: dict, storage) -> None:
    """Recover association renames/additions/removals from stable relative names."""
    root = storage.path_snapshot.resolve(strict=False)
    _validate_edit(data, storage, journal.workspace)
    if state in {"prepared", "rollback_decided"}:
        if data.get("phase") == "publishing":
            # First move every already-published directory back to its unique
            # staging slot. Target names can overlap the old source names, so
            # restoring one source at a time could mistake another association
            # for the copy being rolled back.
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
    """Constrain edit paths to single children of this snapshot and its workspace."""
    moves = data.get("moves")
    additions = data.get("additions")
    if not isinstance(moves, list) or not isinstance(additions, list):
        raise TransactionRecoveryError("Edit journal moves and additions must be lists.")
    if data.get("phase") not in {"staging", "publishing"}:
        raise TransactionRecoveryError("Edit journal has an invalid phase.")
    seen_sources = set()
    seen_targets = set()
    seen_staged = set()

    def validate_item(item: dict, *, is_addition: bool) -> None:
        """Validate one persisted edit record before any recovery rename."""
        if not isinstance(item, dict):
            raise TransactionRecoveryError("Edit journal entry must be an object.")
        if not is_addition:
            source = validate_directory_component(item.get("source"), "edit transaction source")
            if source in seen_sources:
                raise TransactionRecoveryError("Edit journal contains duplicate source names.")
            seen_sources.add(source)
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
            if target in seen_targets:
                raise TransactionRecoveryError("Edit journal contains duplicate destination names.")
            seen_targets.add(target)
        staged = validate_directory_component(item.get("staged"), "edit transaction staging name")
        if staged in seen_staged:
            raise TransactionRecoveryError("Edit journal contains duplicate staging names.")
        seen_staged.add(staged)
        if (workspace / staged).parent.resolve(strict=False) != workspace.resolve(strict=False):
            raise TransactionRecoveryError("Edit staging path escaped its workspace.")

    for move in moves:
        validate_item(move, is_addition=False)
    for addition in additions:
        validate_item(addition, is_addition=True)
    _validate_metadata_paths(data, storage, workspace)


def _complete_edit_directories(journal: SnapshotTransactionJournal, data: dict, root: Path) -> None:
    """Finish all rename and addition publications after commit was decided."""
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


def _refresh_snapshot_model(storage) -> None:
    """Refresh the existing live model from recovered persisted metadata."""
    previous = storage.metadata.from_json(storage.path_snapshot_json)
    current = storage.snapshot
    existing = {association.folder_id: association for association in current.directories}
    directories = []
    for persisted in previous.directories:
        association = existing.get(persisted.folder_id)
        if association is None:
            association = deepcopy(persisted)
        else:
            for model_field in fields(SnapDirAssociation):
                if model_field.name != "_current_index":
                    setattr(association, model_field.name, deepcopy(getattr(persisted, model_field.name)))
            association._set_storage_name(persisted.directory_name)
        directories.append(association)
    for model_field in fields(Snapshot):
        if model_field.name != "directories":
            setattr(current, model_field.name, deepcopy(getattr(previous, model_field.name)))
    current.directories[:] = directories


def _recover_snapshot_tree(journal: SnapshotTransactionJournal, state: str, data: dict) -> None:
    """Finish or undo a whole-snapshot publication using its private staging tree."""
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
