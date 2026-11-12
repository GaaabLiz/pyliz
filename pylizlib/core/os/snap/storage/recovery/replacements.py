"""Validate and recover directory replacements with operation-specific boundaries."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from pylizlib.core.os.filesystem.durability import rename_and_sync
from pylizlib.core.os.filesystem.entries import entry_exists as _lexists
from pylizlib.core.os.filesystem.entries import remove_entry as _remove_path
from pylizlib.core.os.snap.storage.recovery.metadata import _publish_new_metadata, _restore_old_metadata, _validate_metadata_paths
from pylizlib.core.os.snap.storage.transactions import SnapshotTransactionJournal, TransactionRecoveryError
from pylizlib.core.os.snap.storage.tree import is_link_or_junction


def _validate_manifest_restore_entries(data: dict, workspace: Path) -> None:
    """Validate self-contained AD restore records before replaying their swaps.

    Args:
        data (dict): Operation-specific payload, validated before destructive recovery actions.
        workspace (Path): Private transaction workspace containing staged metadata and relative edit names.

    Returns:
        None: No return value; failure handling follows this operation's contract.

    Raises:
        TransactionRecoveryError: The journal is invalid, ambiguous or cannot be recovered safely; unresolved work
            is retained.
    """

    # Reject malformed payload shape before deriving trusted storage boundaries.
    entries = data.get("entries")
    if not isinstance(entries, list):
        raise TransactionRecoveryError("Manifest restore journal has no entry list.")

    # Resolve transaction storage before comparing external restore destinations.
    workspace = workspace.resolve(strict=False)
    scope_root = workspace.parent.parent.resolve(strict=False)
    transaction_root = workspace.parent.resolve(strict=False)
    seen_ids = set()
    destinations = []

    # Validate each identity and generated path before considering pairwise overlap.
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

        # Standalone restore requires absolute staging, destination and backup siblings.
        if not stage.is_absolute() or not destination.is_absolute() or not backup.is_absolute():
            raise TransactionRecoveryError("Manifest restore journal paths must be absolute.")
        if stage.parent.resolve(strict=False) != destination.parent.resolve(strict=False):
            raise TransactionRecoveryError("Manifest restore staging path must be beside its destination.")
        if is_link_or_junction(stage) or not stage.name.startswith(f"{destination.name}_staging_"):
            raise TransactionRecoveryError("Manifest restore staging path is not a generated destination sibling.")
        if backup.parent != destination.parent or not backup.name.startswith(f"{destination.name}_bck_"):
            raise TransactionRecoveryError("Manifest restore backup is not a generated sibling of its destination.")

        # Live targets must not overlap the catalogue transaction storage.
        resolved_destination = destination.resolve(strict=False)
        if resolved_destination == scope_root or scope_root in resolved_destination.parents:
            raise TransactionRecoveryError("Manifest restore destination overlaps catalogue transaction storage.")
        if resolved_destination == transaction_root or transaction_root in resolved_destination.parents:
            raise TransactionRecoveryError("Manifest restore destination overlaps its transaction workspace.")
        destinations.append((folder_id, resolved_destination))

    # Compare all resolved destinations only after their individual records are valid.
    for index, (folder_id, destination) in enumerate(destinations):
        for other_id, other_destination in destinations[index + 1 :]:
            if destination == other_destination or destination in other_destination.parents or other_destination in destination.parents:
                raise TransactionRecoveryError(f"Manifest restore destinations '{folder_id}' and '{other_id}' overlap or are nested.")


def _validate_replacement_entries(operation: str, data: dict, storage, workspace: Path) -> None:
    """Constrain journal swaps to the current snapshot and its live associations.

    Args:
        operation (str): Operation discriminator; determines which path and recovery policy applies.
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
    if not isinstance(data.get("entries"), list):
        raise TransactionRecoveryError("Replacement journal has no entry list.")
    validator = ReplacementValidator(operation, storage, workspace)
    for entry in data["entries"]:
        validator.validate_entry(entry)
    validator.validate_staging_roots(data.get("staging_roots", []))
    _validate_metadata_paths(data, storage, workspace)


def _rollback_replacements(data: dict) -> None:
    """Restore replaced originals and remove copies that had no prior target.

    Args:
        data (dict): Operation-specific payload, validated before destructive recovery actions.

    Returns:
        None: No return value; failure handling follows this operation's contract.
    """
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
    """Finish directory swaps after the durable commit decision was written.

    Args:
        data (dict): Operation-specific payload, validated before destructive recovery actions.

    Returns:
        None: No return value; failure handling follows this operation's contract.

    Raises:
        TransactionRecoveryError: The journal is invalid, ambiguous or cannot be recovered safely; unresolved work
            is retained.
    """
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
    """Delete backups and staging only after the journal records committed state.

    Args:
        data (dict): Operation-specific payload, validated before destructive recovery actions.

    Returns:
        None: No return value; failure handling follows this operation's contract.
    """
    for entry in data.get("entries", []):
        _remove_path(Path(entry["backup"]))
        _remove_path(Path(entry["stage"]))
    for path in data.get("staging_roots", []):
        _remove_path(Path(path))


@dataclass(frozen=True)
class ReplacementPaths:
    """Name the three native paths of one validated replacement record.

    Attributes:
        stage (Path): Owned staging copy before publication.
        destination (Path): Final copy target.
        backup (Path): Recoverable original target.
    """

    stage: Path
    destination: Path
    backup: Path


class ReplacementValidator:
    """Apply common record checks, then the current operation's path policy.

    Attributes:
        operation (str): Operation name selecting recovery policy or identifying the operation in diagnostics.
        workspace (Path): Private transaction directory owning staged metadata and relative edit entries.
        associations (dict[str, SnapDirAssociation]): Expected associations in their persisted/archive order.
        root (Path): Root directory for the tree operation; link and existence policy is described above.

    Notes:
        Use one instance for one plan. Resolving paths and reading directory_name retain existing filesystem/model
        validation side effects; this validator does not mutate the journal dictionary.
    """

    def __init__(self, operation: str, storage, workspace: Path):
        """Capture the current association map and resolved stored-snapshot root.

        Args:
            operation (str): Operation name selecting recovery policy or identifying the operation in diagnostics.
            storage (SnapshotStorage): Live snapshot model, settings, captured layout and protected metadata adapter
                for this operation.
            workspace (Path): Private transaction directory owning staged metadata and relative edit entries.

        Returns:
            None: No return value.
        """
        self.operation = operation
        self.workspace = workspace
        self.associations = {association.folder_id: association for association in storage.snapshot.directories}
        self.root = storage.path_snapshot.resolve(strict=False)

    def validate_entry(self, entry: dict) -> None:
        """Validate identity and field shape before dispatching operation path checks.

        Args:
            entry (dict): One persisted replacement record whose fields are checked before path replay.

        Returns:
            None: No return value.

        Raises:
            TransactionRecoveryError: The journal is invalid, ambiguous or cannot be recovered safely; unresolved work
                is retained.
        """
        if not isinstance(entry, dict) or not isinstance(entry.get("folder_id"), str):
            raise TransactionRecoveryError("Replacement journal entry has no association identity.")
        association = self.associations.get(entry["folder_id"])

        # A commit-decided edit does not use this handler; other replacement
        # operations must still match the persisted association set.
        if association is None:
            raise TransactionRecoveryError(f"Unknown association in transaction: {entry['folder_id']!r}.")
        for key in ("stage", "destination", "backup"):
            if not isinstance(entry.get(key), str) or not entry[key]:
                raise TransactionRecoveryError(f"Replacement journal path '{key}' must be a nonempty string.")
        if type(entry.get("had_original")) is not bool:
            raise TransactionRecoveryError("Replacement journal 'had_original' must be a boolean.")
        if entry.get("merge_child", False) and self.operation != "install":
            raise TransactionRecoveryError("Only install journals may contain merge entries.")
        if "stage_root" in entry and not isinstance(entry["stage_root"], str):
            raise TransactionRecoveryError("Replacement journal stage root must be a string.")
        stage = Path(entry["stage"])
        destination = Path(entry["destination"])
        backup = Path(entry["backup"])
        paths = ReplacementPaths(stage, destination, backup)
        if self.operation in {"install", "restore_associations"}:
            self._validate_external_paths(entry, association, paths)
        elif self.operation == "sync":
            self._validate_sync_paths(association, paths)
        for path in (stage, destination, backup):
            if path.name in {"", ".", ".."}:
                raise TransactionRecoveryError("Transaction journal contains an invalid path.")

    def _validate_external_paths(self, entry: dict, association, paths: ReplacementPaths) -> None:
        """Constrain install/restore targets and their distinct staging ownership.

        Args:
            entry (dict): One persisted replacement record whose fields are checked before path replay.
            association (SnapDirAssociation): Directory association providing stable folder_id, original source and
                stored directory name.
            paths (ReplacementPaths): Ordered filesystem entries to inspect or clean up under the calling policy.

        Returns:
            None: No return value.

        Raises:
            TransactionRecoveryError: The journal is invalid, ambiguous or cannot be recovered safely; unresolved work
                is retained.
        """
        stage, destination, backup = paths.stage, paths.destination, paths.backup
        live = Path(os.path.abspath(association.original_path))
        if self.operation == "install" and entry.get("merge_child"):
            if destination.parent != live or stage.parent != Path(entry.get("stage_root", stage.parent)):
                raise TransactionRecoveryError("Install merge journal escaped its associated directory.")
        elif destination != live:
            raise TransactionRecoveryError("Transaction destination does not match its association.")
        if backup.parent != destination.parent or not backup.name.startswith(f"{destination.name}_bck_"):
            raise TransactionRecoveryError("External backup path is not a generated sibling of its destination.")
        stage_root = Path(entry.get("stage_root", stage.parent))
        if self.operation == "restore_associations":
            if not stage.resolve(strict=False).is_relative_to(self.workspace.resolve(strict=False)):
                raise TransactionRecoveryError("Restore staging path escaped its transaction workspace.")
        else:
            if stage_root.parent != destination.parent or not stage_root.name.startswith(f"{live.name}_staging_"):
                raise TransactionRecoveryError("Install staging path is not a generated sibling of its destination.")
            if not entry.get("merge_child") and stage != stage_root:
                raise TransactionRecoveryError("Install staging directory does not match its journal entry.")

    def _validate_sync_paths(self, association, paths: ReplacementPaths) -> None:
        """Require generated sync siblings directly below the stored snapshot root.

        Args:
            association (SnapDirAssociation): Directory association providing stable folder_id, original source and
                stored directory name.
            paths (ReplacementPaths): Ordered filesystem entries to inspect or clean up under the calling policy.

        Returns:
            None: No return value.

        Raises:
            TransactionRecoveryError: The journal is invalid, ambiguous or cannot be recovered safely; unresolved work
                is retained.
        """
        stage, destination, backup = paths.stage, paths.destination, paths.backup
        expected = self.root / association.directory_name
        if destination != expected or stage.parent != self.root or backup.parent != self.root:
            raise TransactionRecoveryError("Sync transaction paths must be direct children of the snapshot root.")
        if not stage.name.startswith(f"{expected.name}_staging_") or not backup.name.startswith(f"{expected.name}_bck_"):
            raise TransactionRecoveryError("Sync transaction uses an unexpected staging or backup name.")

    def validate_staging_roots(self, staging_roots: object) -> None:
        """Check all shared staging roots after individual replacement entries.

        Args:
            staging_roots (object): Generated staging-root paths owned by this operation and eligible for journal
                cleanup.

        Returns:
            None: No return value.

        Raises:
            TransactionRecoveryError: The journal is invalid, ambiguous or cannot be recovered safely; unresolved work
                is retained.
        """
        if not isinstance(staging_roots, list):
            raise TransactionRecoveryError("Replacement journal staging roots must be a list.")
        for raw_path in staging_roots:
            if not isinstance(raw_path, str) or not raw_path:
                raise TransactionRecoveryError("Replacement journal staging root must be a nonempty string.")
            path = Path(raw_path)
            if self.operation == "sync":
                allowed = path.parent == self.root and any(path.name.startswith(f"{association.directory_name}_staging_") for association in self.associations.values())
            elif self.operation == "install":
                allowed = any(
                    path.parent == live.parent and path.name.startswith(f"{live.name}_staging_")
                    for live in (Path(os.path.abspath(association.original_path)) for association in self.associations.values())
                )
            else:
                allowed = False
            if not allowed:
                raise TransactionRecoveryError("Replacement journal staging root is outside its generated staging paths.")


def recover_manifest_restore(journal: SnapshotTransactionJournal, state: str, data: dict) -> None:
    """Recover a standalone AD restore without requiring catalogue snapshot metadata.

    Args:
        journal (SnapshotTransactionJournal): Transaction journal owning staged paths, persisted decisions and
            cleanup.
        state (str): Known journal decision; validation of names does not impose a new transition graph.
        data (dict): Decoded JSON value or metadata mapping; fields are validated without implicit schema
            coercion.

    Returns:
        None: No return value.

    Raises:
        TransactionRecoveryError: The journal is invalid, ambiguous or cannot be recovered safely; unresolved work
            is retained.
    """
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


def recover_replacements(journal: SnapshotTransactionJournal, state: str, data: dict, storage, operation: str) -> None:
    """Recover install/sync/legacy AD replacements with the matching metadata policy.

    Args:
        journal (SnapshotTransactionJournal): Transaction journal owning staged paths, persisted decisions and
            cleanup.
        state (str): Known journal decision; validation of names does not impose a new transition graph.
        data (dict): Decoded JSON value or metadata mapping; fields are validated without implicit schema
            coercion.
        storage (SnapshotStorage): Live snapshot model, settings, captured layout and protected metadata adapter
            for this operation.
        operation (str): Operation name selecting recovery policy or identifying the operation in diagnostics.

    Returns:
        None: No return value.
    """
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
