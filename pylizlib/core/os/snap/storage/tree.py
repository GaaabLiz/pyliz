"""Filesystem entry checks shared by snapshot storage implementations."""

import os
import stat
from collections.abc import Iterator
from pathlib import Path


def is_link_or_junction(path: Path) -> bool:
    """Identify symbolic links and Windows junctions without traversing them.

    The optional junction API is looked up for compatibility with platforms
    that do not provide Path.is_junction.
    """
    is_junction = getattr(path, "is_junction", None)
    return path.is_symlink() or (is_junction is not None and is_junction())


def iter_files_strict(root: Path) -> Iterator[Path]:
    """Enumerate files without suppressing scan or metadata errors.

    Directory symlinks are not traversed, matching the previous rglob
    policy. File symlinks are read; failures resolving them propagate.
    """
    if not stat.S_ISDIR(root.stat().st_mode):
        raise NotADirectoryError(f"Archive source '{root}' is not a directory.")
    pending = [root]
    while pending:
        with os.scandir(pending.pop()) as entries:
            for entry in entries:
                mode = entry.stat(follow_symlinks=False).st_mode
                path = Path(entry.path)
                if stat.S_ISDIR(mode):
                    pending.append(path)
                elif stat.S_ISREG(mode):
                    yield path
                elif stat.S_ISLNK(mode) and stat.S_ISREG(entry.stat().st_mode):
                    yield path


def assert_no_symlinks(root: Path) -> None:
    """Reject symlinks anywhere in snapshot storage before traversing it."""
    try:
        root_mode = root.lstat().st_mode
    except FileNotFoundError:
        raise
    if not stat.S_ISDIR(root_mode) or is_link_or_junction(root):
        raise NotADirectoryError(f"Snapshot storage '{root}' is not a real directory.")

    pending = [root]
    while pending:
        current = pending.pop()
        if is_link_or_junction(current):
            raise ValueError(f"Snapshot storage contains symbolic link '{current}'.")
        with os.scandir(current) as entries:
            for entry in entries:
                mode = entry.stat(follow_symlinks=False).st_mode
                entry_path = Path(entry.path)
                if stat.S_ISLNK(mode) or is_link_or_junction(entry_path):
                    raise ValueError(f"Snapshot storage contains symbolic link '{entry.path}'.")
                if stat.S_ISDIR(mode):
                    pending.append(Path(entry.path))
