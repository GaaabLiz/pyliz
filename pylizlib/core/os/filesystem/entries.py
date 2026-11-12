"""Inspect and remove named filesystem entries without following root links."""

import shutil
import stat
from pathlib import Path

from pylizlib.core.os.filesystem.tree import is_link_or_junction


def entry_exists(path: Path) -> bool:
    """Check for an entry without following a dangling symbolic link.

    Args:
        path (Path): Native entry to inspect with lstat.

    Returns:
        bool: False only for FileNotFoundError; dangling links count as present.

    Raises:
        OSError: If lstat fails for a reason other than absence.
    """
    try:
        path.lstat()
        return True
    except FileNotFoundError:
        return False


def remove_entry(path: Path) -> None:
    """Remove a named entry without following a link or junction at its root.

    Args:
        path (Path): File, link or directory to delete; absence is accepted.

    Returns:
        None: After unlink/rmtree, or when the entry was already absent.

    Raises:
        OSError: If inspecting or removing an existing entry fails.
    """
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return
    if stat.S_ISDIR(mode) and not is_link_or_junction(path):
        shutil.rmtree(path)
    else:
        path.unlink()
