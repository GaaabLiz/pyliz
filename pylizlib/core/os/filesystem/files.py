"""File-specific inspection helpers."""

import os
import platform
from datetime import datetime


def is_file_dup_in_dir(path: str, file_name: str) -> bool:
    """Return whether a file with the given name exists anywhere under a directory.

    Args:
        path (str | Path): Directory tree to search.
        file_name (str): File name to find.

    Returns:
        bool: Whether any scanned directory contains a matching name.
    """
    for root, dirs, files in os.walk(path):
        if file_name in files:
            return True
    return False


def get_file_c_date(path_to_file) -> datetime:
    """Return a file's creation date when available, otherwise its modification date.

    On Windows, use the creation timestamp. On platforms that do not expose a
    birth time, use the last modification timestamp.

    Args:
        path_to_file (str | Path): Existing file whose timestamp should be read.

    Returns:
        datetime: Local datetime corresponding to the selected filesystem timestamp.
    """
    if platform.system() == "Windows":
        timestamp = os.path.getctime(path_to_file)
    else:
        stat = os.stat(path_to_file)
        try:
            timestamp = stat.st_birthtime
        except AttributeError:
            timestamp = stat.st_mtime

    return datetime.fromtimestamp(timestamp)
