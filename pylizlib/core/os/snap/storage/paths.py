"""Contained paths for snapshot roots and direct children."""

from pathlib import Path

from pylizlib.core.os.snap.domain import validate_directory_component
from pylizlib.core.os.snap.storage.tree import is_link_or_junction


def get_snapshot_path(folder_name: str, catalogue_path: Path) -> Path:
    """
    Constructs the full path to a snapshot's directory within the catalogue.
    Validates the folder name to prevent path traversal.

    Args:
        folder_name: The name of the snapshot's folder (usually the snapshot ID).
        catalogue_path: The base path of the snapshot catalogue.

    Returns:
        The full path to the snapshot's directory.

    Raises:
        ValueError: If the folder_name attempts path traversal or is invalid.
    """
    validate_directory_component(folder_name, "Snapshot ID")
    if not folder_name.strip():
        raise ValueError("Snapshot ID cannot be empty.")

    try:
        catalogue_resolved = catalogue_path.resolve(strict=False)
        candidate_path = catalogue_path / folder_name
        if is_link_or_junction(candidate_path):
            raise ValueError(f"Snapshot root '{candidate_path}' cannot be a symbolic link.")
        destination_path = catalogue_resolved / folder_name
        if is_link_or_junction(destination_path):
            raise ValueError(f"Snapshot root '{destination_path}' cannot be a symbolic link.")
        destination_resolved = destination_path.resolve(strict=False)

        # Use structural containment to distinguish the catalogue from
        # similarly prefixed sibling paths (for example, cat_evil).
        expected_path = catalogue_resolved / folder_name
        if destination_resolved == catalogue_resolved or not destination_resolved.is_relative_to(catalogue_resolved):
            raise ValueError(f"Snapshot path must be strictly contained in its catalogue. Resolved: {destination_resolved}")
        if destination_resolved != expected_path:
            raise ValueError(f"Snapshot path does not resolve to its catalogue entry: {destination_resolved}")
    except Exception as e:
        if isinstance(e, ValueError):
            raise
        raise ValueError(f"Invalid snapshot path: {e}")

    return expected_path


def validate_snapshot_root(folder_name: str, catalogue_path: Path) -> Path:
    """Return the snapshot root, rejecting a root replaced by a symlink."""
    root = get_snapshot_path(folder_name, catalogue_path)
    if is_link_or_junction(root):
        raise ValueError(f"Snapshot root '{root}' cannot be a symbolic link.")
    return root


def get_snapshot_child_path(folder_name: str, catalogue_path: Path, child_name: str) -> Path:
    """Resolve and contain a single child path beneath its snapshot root."""
    validate_directory_component(child_name)
    root = validate_snapshot_root(folder_name, catalogue_path)
    destination = root / child_name
    if is_link_or_junction(destination):
        raise ValueError(f"Snapshot child '{destination}' resolves through a symbolic link.")
    resolved = destination.resolve(strict=False)
    if resolved == root or not resolved.is_relative_to(root) or resolved != destination:
        raise ValueError(f"Snapshot child '{destination}' resolves outside its direct storage path.")
    return destination


def get_snapshot_json_path(folder_name: str, catalogue_path: Path, json_filename: str) -> Path:
    """
    Constructs the full path to a snapshot's JSON file.

    Args:
        folder_name: The name of the snapshot's folder.
        catalogue_path: The base path of the snapshot catalogue.
        json_filename: The name of the JSON file.

    Returns:
        The full path to the snapshot's JSON file.
    """
    return get_snapshot_child_path(folder_name, catalogue_path, json_filename)
