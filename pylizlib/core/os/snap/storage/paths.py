"""Contained paths for snapshot roots and direct children."""

from pathlib import Path

from pylizlib.core.os.snap.domain import validate_directory_component
from pylizlib.core.os.snap.storage.coordination import CATALOGUE_LOCK_FILENAME
from pylizlib.core.os.snap.storage.recovery.models import TRANSACTION_DIRECTORY
from pylizlib.core.os.snap.storage.tree import is_link_or_junction


def is_transaction_storage_name(name: str) -> bool:
    """Recognize reserved journal names, including portable Windows aliases.

    Args:
        name (str): One filesystem component to compare with the transaction namespace.

    Returns:
        bool: True for the reserved name, ignoring case and trailing spaces/dots. This conservative policy is
            applied on every host so a stored tree remains safe when transferred to Windows.
    """
    return name.rstrip(" .").casefold() == TRANSACTION_DIRECTORY.casefold()


def assert_no_transaction_storage(root: Path) -> None:
    """Reject operational journal storage in an incoming snapshot root.

    Args:
        root (Path): Snapshot or extracted catalogue root whose direct children are inspected.

    Returns:
        None: When no direct child occupies the reserved transaction namespace. Nested user data inside an
            association is not interpreted as snapshot operational storage.

    Raises:
        ValueError: A direct child has a reserved transaction name, regardless of its entry type.
        OSError: The root cannot be enumerated.
    """
    for entry in root.iterdir():
        if is_transaction_storage_name(entry.name):
            raise ValueError(f"Incoming snapshot data cannot contain transaction storage: '{entry}'.")


def is_operational_storage_name(name: str) -> bool:
    """Recognize journal and catalogue-lock names that incoming data must never replace.

    Args:
        name (str): Direct storage component, checked with portable Windows alias rules on every platform.

    Returns:
        bool: True for reserved transaction or coordination names, including case and trailing-dot/space aliases.
    """
    return is_transaction_storage_name(name) or name.rstrip(" .").casefold() == CATALOGUE_LOCK_FILENAME.casefold()


def assert_no_operational_storage(root: Path) -> None:
    """Reject local recovery and lock sidecars at the root of incoming archive data.

    Args:
        root (Path): Extracted catalogue or snapshot root; association descendants remain ordinary user content.

    Returns:
        None: No direct child occupies a reserved operational namespace.

    Raises:
        ValueError: Incoming data contains reserved transaction storage or a coordination sidecar.
        OSError: The root cannot be enumerated.
    """
    for entry in root.iterdir():
        if is_operational_storage_name(entry.name):
            raise ValueError(f"Incoming snapshot data cannot contain transaction storage or a catalogue lock: '{entry}'.")


def get_snapshot_path(folder_name: str, catalogue_path: Path) -> Path:
    """Constructs the full path to a snapshot's directory within the catalogue.
    Validates the folder name to prevent path traversal.

    Args:
        folder_name (str): The name of the snapshot's folder (usually the snapshot ID).
        catalogue_path (Path): The base path of the snapshot catalogue.

    Returns:
        Path: The full path to the snapshot's directory.

    Raises:
        ValueError: If the folder_name attempts path traversal or is invalid.
    """
    validate_directory_component(folder_name, "Snapshot ID")
    if not folder_name.strip():
        raise ValueError("Snapshot ID cannot be empty.")
    if is_operational_storage_name(folder_name):
        raise ValueError("Snapshot ID cannot use a reserved transaction directory or catalogue lock name.")

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
    """Return the snapshot root, rejecting a root replaced by a symlink.

    Args:
        folder_name (str): Snapshot ID used as a single catalogue-directory component.
        catalogue_path (Path): Catalogue directory containing snapshot ID subdirectories.

    Returns:
        Path: Contained snapshot directory path, rejecting a root currently replaced by a link.

    Raises:
        ValueError: A value, path, resource limit or metadata field violates the validation rules described above.
    """
    root = get_snapshot_path(folder_name, catalogue_path)
    if is_link_or_junction(root):
        raise ValueError(f"Snapshot root '{root}' cannot be a symbolic link.")
    return root


def get_snapshot_child_path(folder_name: str, catalogue_path: Path, child_name: str) -> Path:
    """Resolve and contain a single child path beneath its snapshot root.

    Args:
        folder_name (str): Snapshot ID used as a single catalogue-directory component.
        catalogue_path (Path): Catalogue directory containing snapshot ID subdirectories.
        child_name (str): Single direct-child component to resolve below the validated snapshot root.

    Returns:
        Path: Validated direct child path with no current link escape from the stored root.

    Raises:
        ValueError: A value, path, resource limit or metadata field violates the validation rules described above.
    """
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
    """Constructs the full path to a snapshot's JSON file.

    Args:
        folder_name (str): The name of the snapshot's folder.
        catalogue_path (Path): The base path of the snapshot catalogue.
        json_filename (str): The name of the JSON file.

    Returns:
        Path: The full path to the snapshot's JSON file.
    """
    return get_snapshot_child_path(folder_name, catalogue_path, json_filename)
