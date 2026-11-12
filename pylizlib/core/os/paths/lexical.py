"""Cross-platform lexical paths without resolving filesystem links."""

import os
from collections.abc import Callable
from pathlib import Path, PurePosixPath, PureWindowsPath

from pylizlib.core.os.windows.drives import get_drive_type, get_mapped_drive_unc_root, is_unc_path


def is_absolute_path(value: str) -> bool:
    """Recognize an explicit POSIX or Windows root on any host.

    Args:
        value (str): Path spelling; invalid non-string values are tolerated.

    Returns:
        bool: False for empty, NUL-containing or drive-relative paths, otherwise
        whether either supported flavour considers the path absolute.
    """
    if not isinstance(value, str) or not value or "\x00" in value:
        return False
    windows_path = PureWindowsPath(value)
    if windows_path.drive and not windows_path.root:
        return False
    return PurePosixPath(value).is_absolute() or windows_path.is_absolute()


def normalize_mapped_drive(path: PureWindowsPath, *, unc_root: Callable[[str], str] | None = None) -> str:
    """Replace a mapped drive prefix while preserving its lexical suffix.

    Args:
        path (PureWindowsPath): Absolute drive-letter path to normalize.
        unc_root (Callable[[str], str] | None): Drive-letter lookup, or the native
            Windows adapter when omitted.

    Returns:
        str: UNC path with forward slashes and unresolved parent/link components.

    Raises:
        ValueError: If the mapping cannot be resolved; native errors are chained.
    """
    try:
        unc_root = PureWindowsPath((unc_root or get_mapped_drive_unc_root)(path.drive[0]))
    except (AttributeError, OSError) as error:
        raise ValueError(f"Cannot resolve mapped network drive '{path.drive}' to a UNC path. Use the UNC path directly.") from error
    drive_root = PureWindowsPath(f"{path.drive}\\")
    suffix = path.relative_to(drive_root)
    return unc_root.joinpath(*suffix.parts).as_posix()


def normalize_rooted_path(value: str, *, allow_relative: bool = True, path_label: str = "Path", drive_type: Callable[[str], int] | None = None, unc_root: Callable[[str], str] | None = None) -> str:
    """Return an absolute, lexically normalized path without following symlinks.

    Args:
        value (str): Non-empty POSIX or Windows path without NUL characters.
        allow_relative (bool): Whether to anchor a relative path to CWD.
        path_label (str): Subject used in validation messages; defaults to Path.
        drive_type (Callable[[str], int] | None): Optional drive-letter type lookup.
            Omitted uses the native Windows adapter, called only on Windows.
        unc_root (Callable[[str], str] | None): Optional mapped-drive UNC lookup.

    Returns:
        str: Rooted spelling with forward slashes; links and parent components
        remain unresolved. Windows remote drives are converted to UNC.

    Raises:
        TypeError: If value is not a string.
        ValueError: If the input is invalid or a required UNC lookup fails.
        OSError: If CWD or a native drive operation cannot be read.

    Notes:
        The path need not exist. This operation does not establish containment.
    """
    if not isinstance(value, str):
        raise TypeError(f"{path_label} must be a string.")
    if not value or "\x00" in value:
        raise ValueError(f"{path_label} must be a non-empty path without NUL characters.")

    windows_path = PureWindowsPath(value)
    if windows_path.drive and not windows_path.root:
        raise ValueError(f"Drive-relative paths are not supported: {value!r}.")

    if windows_path.is_absolute():
        if os.name == "nt" and not is_unc_path(windows_path) and (drive_type or get_drive_type)(windows_path.drive[0]) == 4:
            return normalize_mapped_drive(windows_path, unc_root=unc_root)
        return windows_path.as_posix()

    posix_path = PurePosixPath(value)
    if posix_path.is_absolute():
        return posix_path.as_posix()

    if not allow_relative:
        raise ValueError(f"{path_label} must be absolute; relative path {value!r} cannot be resolved safely.")

    # Anchor without resolving links or collapsing ``..`` across a symlink.
    return (Path.cwd() / Path(value)).as_posix()
