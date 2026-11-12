"""Directory-entry flushing and rename ordering on supported platforms."""

import errno
import os
from pathlib import Path

from pylizlib.core.log.pylizLogger import logger

_UNSUPPORTED_DIRECTORY_SYNC = {errno.EBADF, errno.EINVAL, getattr(errno, "ENOTSUP", errno.EINVAL), getattr(errno, "EOPNOTSUPP", errno.EINVAL)}


def sync_directory(path: Path) -> bool:
    """Request a directory-entry flush, returning False when unsupported.

    Args:
        path (Path): Directory to open read-only and flush on supported platforms.

    Returns:
        bool: True after successful fsync; False on Windows or unsupported backends.

    Raises:
        OSError: If a supported open, sync or close operation fails.
    """
    if os.name == "nt" or not getattr(os, "O_DIRECTORY", 0):
        return False
    flags = os.O_RDONLY | os.O_DIRECTORY
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        if error.errno in _UNSUPPORTED_DIRECTORY_SYNC:
            return False
        raise
    try:
        try:
            os.fsync(descriptor)
        except OSError as error:
            if error.errno in _UNSUPPORTED_DIRECTORY_SYNC:
                return False
            raise
        return True
    finally:
        os.close(descriptor)


def rename_and_sync(source: Path, destination: Path) -> None:
    """Rename one transaction entry and flush both affected parent directories.

    Directory fsync orders filesystem namespace changes before a later journal
    state can be considered durable. Some platforms and remote filesystems do
    not support it; those environments retain atomic rename semantics but
    cannot confirm server-side persistence.

    Args:
        source (Path): Entry renamed with native Path.rename semantics.
        destination (Path): Target passed to rename, subject to native collision rules.

    Returns:
        None: After rename and both distinct parent sync attempts.

    Raises:
        OSError: If rename or a supported flush fails; a flush failure may occur
            after the new name is already visible.
    """
    source = Path(source)
    destination = Path(destination)
    source.rename(destination)
    parents = {source.parent, destination.parent}
    for parent in parents:
        if not sync_directory(parent):
            logger.warning(f"Directory-entry durability is unavailable for transaction path '{parent}'.")
