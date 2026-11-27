"""Shared validation for filesystem destinations that an operation can replace or remove."""

import platform
from collections.abc import Iterable
from pathlib import Path

from pylizlib.core.os.paths.safety import assert_no_link_components, is_critical_system_path
from pylizlib.core.os.snap.domain import Snapshot
from pylizlib.core.os.snap.storage.path_identity import same_filesystem_entry


def _contains_path(parent: Path, child: Path) -> bool:
    """Check resolved containment, including filesystem-equivalent spellings.

    Args:
        parent (Path): Resolved candidate ancestor.
        child (Path): Resolved path that may lie under parent.

    Returns:
        bool: Whether the paths are equal or child lies below parent.
    """
    return child.is_relative_to(parent) or any(same_filesystem_entry(parent, path) for path in (child, *child.parents))


def validate_backup_separation(paths: Iterable[str | Path], backup_path: Path | None, *, archive_path: Path | None = None) -> None:
    """Keep backup storage and the input archive outside affected snapshot trees.

    Args:
        paths (Iterable[str | Path]): Association or replacement paths to check.
        backup_path (Path | None): Configured backup directory, disjoint from each affected tree.
        archive_path (Path | None): Input ZIP that a restore must not move or remove.

    Returns:
        None: All affected trees are separate from the protected backup paths.

    Raises:
        ValueError: A tree overlaps the backup directory or contains the input archive.
        OSError: The filesystem prevents resolving a path.
    """
    if backup_path is None and archive_path is None:
        return

    backup_root = Path(backup_path).resolve(strict=False) if backup_path is not None else None
    archive_locations = ()
    if archive_path is not None:
        archive_path = Path(archive_path)
        archive_locations = (archive_path.resolve(strict=False), archive_path.parent.resolve(strict=False))

    for path in paths:
        tree = Path(path).resolve(strict=False)
        if backup_root is not None and (_contains_path(tree, backup_root) or _contains_path(backup_root, tree)):
            raise ValueError(f"Snapshot path '{path}' overlaps the backup directory '{backup_path}'.")
        if any(_contains_path(tree, location) for location in archive_locations):
            raise ValueError(f"Restore destination '{path}' contains the backup archive '{archive_path}'.")


def validate_associations_outside_backups(snapshot: Snapshot, backup_path: Path | None) -> None:
    """Reject saved associations overlapping the configured backup directory.

    Args:
        snapshot (Snapshot): Model whose recorded paths are being published or captured.
        backup_path (Path | None): Configured backup directory on the current system.

    Returns:
        None: Every native association path is separate from backup storage.

    Notes:
        A foreign path without a native root is resolved only after explicit
        remapping by the restore planner.
    """
    if backup_path is not None:
        paths = (Path(association.original_path) for association in snapshot.directories)
        validate_backup_separation((path for path in paths if path.is_absolute()), backup_path)


def validate_destructive_destinations(
    destinations: Iterable[tuple[str, str | Path]],
    *,
    catalogue_path: Path,
    origin_os: str | None,
    operation: str,
    backup_path: Path | None = None,
    archive_path: Path | None = None,
) -> list[Path]:
    """Validate origin OS, critical paths, overlap and linked path components.

    Returns lexical absolute paths in input order. Resolved paths are used
    for safety comparisons, while the returned lexical paths preserve the
    filesystem entry that the caller intends to replace or remove.

    Args:
        destinations (Iterable[tuple[str, str | Path]]): Iterable of (association identity, target path) pairs,
            checked for OS, critical paths and overlaps.
        catalogue_path (Path): Catalogue directory containing snapshot ID subdirectories.
        origin_os (str | None): Originating OS label to compare with platform.system(); None omits that
            compatibility check.
        operation (str): Operation name selecting recovery policy or identifying the operation in diagnostics.
        backup_path (Path | None): Configured backup directory that must remain separate from the destinations.
        archive_path (Path | None): Input archive that must remain outside the destinations.

    Returns:
        list[Path]: Absolute lexical destination paths in input order, after OS, critical-path, catalogue and
            pairwise-overlap and link-component checks. Parent components are retained for subsequent I/O.

    Raises:
        RuntimeError: The requested operation cannot complete; a wrapped failure retains its original cause where
            documented.
        ValueError: A value, path, resource limit or metadata field violates the validation rules described above.
    """
    if origin_os is not None and origin_os != platform.system():
        raise RuntimeError(f"Cannot {operation}: created on {origin_os}, but current OS is {platform.system()}.")

    destination_paths = []
    resolved_destinations = []
    for identity, raw_path in destinations:
        path = Path(raw_path).absolute()
        try:
            resolved = path.resolve(strict=False)
        except Exception as error:
            raise ValueError(f"Cannot verify destructive destination '{raw_path}' ({identity}): {error}") from error
        if is_critical_system_path(path):
            raise ValueError(f"Cannot {operation} at '{raw_path}' ({identity}): it is a critical system path.")
        destination_paths.append(path)
        resolved_destinations.append((identity, resolved))

    try:
        catalogue_root = Path(catalogue_path).resolve(strict=False)
    except Exception as error:
        raise ValueError(f"Cannot verify snapshot catalogue path '{catalogue_path}': {error}") from error

    for identity, destination in resolved_destinations:
        if same_filesystem_entry(destination, catalogue_root) or destination in catalogue_root.parents or catalogue_root in destination.parents:
            raise ValueError(f"Cannot {operation} at '{destination}' ({identity}): it overlaps the snapshot catalogue.")

    for index, (identity, destination) in enumerate(resolved_destinations):
        for other_identity, other_destination in resolved_destinations[index + 1 :]:
            if same_filesystem_entry(destination, other_destination) or destination in other_destination.parents or other_destination in destination.parents:
                raise ValueError(f"{operation.capitalize()} destinations cannot be coincident or nested: '{identity}' at '{destination}' and '{other_identity}' at '{other_destination}'.")

    # Keep lexical semantics for I/O and reject links before they can redirect any component.
    for path in destination_paths:
        assert_no_link_components(path)

    validate_backup_separation(destination_paths, backup_path, archive_path=archive_path)
    return destination_paths
