"""Strict filesystem tree traversal, rejecting symbolic links and junctions."""

import os
import stat
from collections.abc import Iterator
from pathlib import Path

from pylizlib.core.os.paths.containment import assert_destination_outside_source as assert_destination_outside_source


def is_link_or_junction(path: Path) -> bool:
    """Identify symbolic links and Windows junctions without traversing them.

    The optional junction API is looked up for compatibility with platforms
    that do not provide Path.is_junction.

    Args:
        path (Path): Entry to inspect, including a dangling symbolic link.

    Returns:
        bool: Whether the entry is a symbolic link or a Windows junction.

    Raises:
        OSError: If a platform entry check fails rather than reporting absence.
    """
    is_junction = getattr(path, "is_junction", None)
    return path.is_symlink() or (is_junction is not None and is_junction())


def iter_files_strict(root: Path) -> Iterator[Path]:
    """Enumerate regular files, rejecting links and propagating scan errors.

    Args:
        root (Path): Existing real directory to traverse with a depth-first stack.

    Yields:
        Path: Regular files in filesystem enumeration order; directories and
        special entries are omitted. No sorting or source mutation is performed.

    Raises:
        NotADirectoryError: If root is not a real directory.
        ValueError: If a link or junction is encountered.
        OSError: If stat or enumeration fails, including a missing root.
    """
    yield from _iter_entries_strict(root, include_directories=False)


def iter_tree_entries_strict(root: Path) -> Iterator[Path]:
    """Yield regular files and child directories, rejecting all links.

    The root itself is omitted. Directory entries are yielded before descent,
    preserving empty directories. Links are rejected instead of followed or
    silently skipped so archive and copy callers share one tree policy.
    Filesystem scan errors propagate to the caller.

    Args:
        root (Path): Existing real directory to traverse without following links.

    Yields:
        Path: Regular files and child directories in filesystem enumeration order.
        The root is excluded; empty child directories are retained.

    Raises:
        NotADirectoryError: If root is not a real directory.
        ValueError: If a link or junction is encountered.
        OSError: If stat or enumeration fails, including a missing root.
    """
    yield from _iter_entries_strict(root, include_directories=True)


def assert_no_symlinks(root: Path) -> None:
    """Reject symlinks and junctions anywhere in a tree before copying it.

    Args:
        root (Path): Real directory whose descendants are inspected without
            following links. Other special entries are not rejected here.

    Returns:
        None: If no symbolic link or junction was observed.

    Raises:
        NotADirectoryError: If root is not a real directory.
        ValueError: If a descendant is a link or a directory becomes a link.
        OSError: If stat or enumeration fails.

    Notes:
        Callers still need post-copy checks for changes concurrent with traversal.
    """
    try:
        root_mode = root.lstat().st_mode
    except FileNotFoundError:
        raise
    if not stat.S_ISDIR(root_mode) or is_link_or_junction(root):
        raise NotADirectoryError(f"Directory tree '{root}' is not a real directory.")

    pending = [root]
    while pending:
        current = pending.pop()
        if is_link_or_junction(current):
            raise ValueError(f"Directory tree contains symbolic link '{current}'.")
        with os.scandir(current) as entries:
            for entry in entries:
                mode = entry.stat(follow_symlinks=False).st_mode
                entry_path = Path(entry.path)
                if stat.S_ISLNK(mode) or is_link_or_junction(entry_path):
                    raise ValueError(f"Directory tree contains symbolic link '{entry.path}'.")
                if stat.S_ISDIR(mode):
                    pending.append(Path(entry.path))


def _iter_entries_strict(root: Path, *, include_directories: bool) -> Iterator[Path]:
    """Apply one traversal/link policy for both public entry enumerators.

    Args:
        root (Path): Existing real directory checked lazily on first iteration.
        include_directories (bool): Yield child directories before descent when True;
            otherwise retain only regular files. Special entries remain omitted.

    Yields:
        Path: Accepted entries in the original filesystem/stack traversal order.

    Raises:
        NotADirectoryError: If root is not a real directory.
        ValueError: If a link or junction is encountered.
        OSError: If stat or enumeration fails.
    """
    root = Path(root)
    root_mode = root.lstat().st_mode
    if is_link_or_junction(root) or not stat.S_ISDIR(root_mode):
        raise NotADirectoryError(f"Archive source '{root}' is not a directory.")
    pending = [root]
    while pending:
        with os.scandir(pending.pop()) as entries:
            for entry in entries:
                mode = entry.stat(follow_symlinks=False).st_mode
                path = Path(entry.path)
                if stat.S_ISLNK(mode) or is_link_or_junction(path):
                    raise ValueError(f"Directory tree contains symbolic link '{path}'.")
                if stat.S_ISDIR(mode):
                    if include_directories:
                        yield path
                    pending.append(path)
                elif stat.S_ISREG(mode):
                    yield path
