"""Shared validation for filesystem destinations that an operation can replace or remove."""

import os
import platform
from collections.abc import Iterable
from pathlib import Path

from pylizlib.core.os.paths.safety import is_critical_system_path
from pylizlib.core.os.snap.storage.path_identity import same_filesystem_entry


def validate_destructive_destinations(
    destinations: Iterable[tuple[str, str | Path]],
    *,
    catalogue_path: Path,
    origin_os: str | None,
    operation: str,
) -> list[Path]:
    """Validate origin OS, critical paths, catalogue overlap and pairwise overlap.

    Returns normalized absolute paths in input order. Resolved paths are used
    for safety comparisons, while the returned lexical paths preserve the
    filesystem entry that the caller intends to replace or remove.

    Args:
        destinations (Iterable[tuple[str, str | Path]]): Iterable of (association identity, target path) pairs,
            checked for OS, critical paths and overlaps.
        catalogue_path (Path): Catalogue directory containing snapshot ID subdirectories.
        origin_os (str | None): Originating OS label to compare with platform.system(); None omits that
            compatibility check.
        operation (str): Operation name selecting recovery policy or identifying the operation in diagnostics.

    Returns:
        list[Path]: Absolute lexical destination paths in input order, after OS, critical-path, catalogue and
            pairwise-overlap checks.

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
        path = Path(os.path.abspath(raw_path))
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

    return destination_paths
