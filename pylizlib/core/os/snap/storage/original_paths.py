"""Snapshot source-path policy over general lexical and Windows operations."""

import os as os

from pylizlib.core.os.paths.lexical import is_absolute_path, normalize_rooted_path
from pylizlib.core.os.windows.drives import get_drive_type as _windows_drive_type
from pylizlib.core.os.windows.drives import get_mapped_drive_unc_root as _mapped_drive_unc_root


def is_absolute_original_path(value: str) -> bool:
    """Check whether a persisted source has an explicit POSIX or Windows root.

    Args:
        value (str): Serialized source path; invalid non-string values are tolerated.

    Returns:
        bool: False for empty, NUL-containing, relative or drive-relative values.
    """
    return is_absolute_path(value)


def normalize_original_path(value: str, *, allow_relative: bool = True) -> str:
    """Normalize an association source without resolving links or parent components.

    Args:
        value (str): Non-empty POSIX or Windows source without NUL characters.
        allow_relative (bool): Anchor relative paths to the current CWD when True. Persisted and subsequently
            mutated associations require False.

    Returns:
        str: Rooted path with forward slashes, using UNC for mapped Windows drives.

    Raises:
        TypeError: If value is not a string.
        ValueError: If the path is invalid, drive-relative, disallowed relative, or a required mapped-drive lookup
            fails.
        OSError: If reading CWD or a native drive operation fails.

    Notes:
        Existence and permissions are checked by the operation using this path. This function may query drive
        mappings in the current Windows logon session.
    """
    return normalize_rooted_path(
        value,
        allow_relative=allow_relative,
        path_label="Snapshot directory original_path",
        drive_type=_windows_drive_type,
        unc_root=_mapped_drive_unc_root,
    )
