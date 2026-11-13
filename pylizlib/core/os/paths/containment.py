"""Structural checks for relationships between filesystem paths."""

from pathlib import Path


def assert_destination_outside_source(source: Path | str, destination: Path | str) -> None:
    """Reject recursive tree copies, resolving both paths through aliases.

    Args:
        source (Path | str): Source tree, resolved without requiring every entry to exist.
        destination (Path | str): Proposed copy target, resolved using the same policy.

    Returns:
        None: If destination is neither source nor structurally inside source.

    Raises:
        ValueError: If destination resolves to source or one of its descendants.
        OSError: If the filesystem prevents resolving either path.

    Notes:
        This check does not reserve paths against concurrent filesystem changes.
    """
    source = Path(source)
    destination = Path(destination)
    source_resolved = source.resolve(strict=False)
    destination_resolved = destination.resolve(strict=False)
    if destination_resolved.is_relative_to(source_resolved):
        raise ValueError(f"Copy destination '{destination}' is inside source directory '{source}'.")
