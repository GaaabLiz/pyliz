"""Filesystem entry checks shared by snapshot storage implementations."""

from pathlib import Path


def is_link_or_junction(path: Path) -> bool:
    """Identify symbolic links and Windows junctions without traversing them.

    The optional junction API is looked up for compatibility with platforms
    that do not provide Path.is_junction.
    """
    is_junction = getattr(path, "is_junction", None)
    return path.is_symlink() or (is_junction is not None and is_junction())
