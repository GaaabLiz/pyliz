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


def assert_destination_outside_source(source: Path, destination: Path) -> None:
    """Reject recursive tree copies, resolving both paths through aliases."""
    source = Path(source)
    destination = Path(destination)
    source_resolved = source.resolve(strict=False)
    destination_resolved = destination.resolve(strict=False)
    if destination_resolved.is_relative_to(source_resolved):
        raise ValueError(f"Copy destination '{destination}' is inside source directory '{source}'.")


def iter_files_strict(root: Path) -> Iterator[Path]:
    """Enumerate regular files, rejecting links and propagating scan errors."""
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
                    pending.append(path)
                elif stat.S_ISREG(mode):
                    yield path


def iter_tree_entries_strict(root: Path) -> Iterator[Path]:
    """Yield regular files and child directories, rejecting all links.

    The root itself is omitted. Directory entries are yielded before descent,
    preserving empty directories. Links are rejected instead of followed or
    silently skipped so archive and copy callers share one tree policy.
    Filesystem scan errors propagate to the caller.
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
                    yield path
                    pending.append(path)
                elif stat.S_ISREG(mode):
                    yield path


def assert_no_symlinks(root: Path) -> None:
    """Reject symlinks and junctions anywhere in a tree before traversing it."""
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
