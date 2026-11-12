"""Prepare, validate and replay snapshot metadata associated with a journal."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import fields
from pathlib import Path

from pylizlib.core.os.snap.domain import SnapDirAssociation, Snapshot, validate_directory_component
from pylizlib.core.os.snap.storage.transactions import SnapshotTransactionJournal, TransactionRecoveryError


def prepare_snapshot_metadata(storage, workspace: Path, *, field_name: str | None = None, field_value=None) -> dict:
    """Save exact old and proposed JSON bytes inside a transaction workspace.

    Args:
        storage (SnapshotStorage | None): Snapshot model, layout and metadata adapter; required for operations using snapshot metadata.
        workspace (Path): Private transaction workspace containing staged metadata and relative edit names.
        field_name (str | None): Single metadata field to patch, or None to serialize the complete live model.
        field_value (object): Value for the requested partial metadata update; ignored for a complete model save.


    Returns:
        dict[str, str]: Workspace-relative old/new filenames and the active metadata basename under keys old, new and target.
    """
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


def _validate_metadata_paths(data: dict, storage, workspace: Path) -> None:
    """Ensure staged metadata and active JSON both belong to this snapshot.

    Args:
        data (dict): Operation-specific payload, validated before destructive recovery actions.
        storage (SnapshotStorage | None): Snapshot model, layout and metadata adapter; required for operations using snapshot metadata.
        workspace (Path): Private transaction workspace containing staged metadata and relative edit names.


    Returns:
        None: After the requested validation, persistence or recovery phase completes; failures propagate unless explicitly handled above.
    """
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


def _publish_new_metadata(journal: SnapshotTransactionJournal, data: dict, storage) -> None:
    """Publish the prepared JSON after all new directory entries are available.

    Args:
        journal (SnapshotTransactionJournal): Live journal owning the workspace, durable state and cleanup.
        data (dict): Operation-specific payload, validated before destructive recovery actions.
        storage (SnapshotStorage | None): Snapshot model, layout and metadata adapter; required for operations using snapshot metadata.


    Returns:
        None: After the requested validation, persistence or recovery phase completes; failures propagate unless explicitly handled above.
    """
    metadata = data.get("metadata")
    if metadata is None:
        return
    new_bytes = storage.metadata.read_bytes(journal.workspace / metadata["new"])
    storage.metadata.write_bytes(storage.path_snapshot_json, new_bytes)


def _restore_old_metadata(journal: SnapshotTransactionJournal, data: dict, storage) -> None:
    """Restore exact old metadata bytes while recovering a decided rollback.

    Args:
        journal (SnapshotTransactionJournal): Live journal owning the workspace, durable state and cleanup.
        data (dict): Operation-specific payload, validated before destructive recovery actions.
        storage (SnapshotStorage | None): Snapshot model, layout and metadata adapter; required for operations using snapshot metadata.


    Returns:
        None: After the requested validation, persistence or recovery phase completes; failures propagate unless explicitly handled above.
    """
    metadata = data.get("metadata")
    if metadata is None:
        return
    old_bytes = storage.metadata.read_bytes(journal.workspace / metadata["old"])
    if storage.metadata.read_bytes(storage.path_snapshot_json) != old_bytes:
        storage.metadata.write_bytes(storage.path_snapshot_json, old_bytes)


def _refresh_snapshot_model(storage) -> None:
    """Refresh the existing live model from recovered persisted metadata.

    Args:
        storage (SnapshotStorage | None): Snapshot model, layout and metadata adapter; required for operations using snapshot metadata.


    Returns:
        None: After the requested validation, persistence or recovery phase completes; failures propagate unless explicitly handled above.
    """
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
