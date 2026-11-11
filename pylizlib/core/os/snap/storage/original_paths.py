"""Canonicalize source paths so associations do not depend on the process CWD."""

import ctypes
import os
from pathlib import Path, PurePosixPath, PureWindowsPath


def _is_unc_path(path: PureWindowsPath) -> bool:
    """Return whether a Windows path is rooted at a UNC server/share."""
    return path.drive.startswith("\\\\")


def is_absolute_original_path(value: str) -> bool:
    """Return whether a serialized source path has an explicit platform root."""
    if not isinstance(value, str) or not value or "\x00" in value:
        return False
    windows_path = PureWindowsPath(value)
    if windows_path.drive and not windows_path.root:
        return False
    return PurePosixPath(value).is_absolute() or windows_path.is_absolute()


def _windows_drive_type(drive: str) -> int:
    """Return the Windows drive type for a drive letter, such as ``Z``."""
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_drive_type = kernel32.GetDriveTypeW
    get_drive_type.argtypes = [wintypes.LPCWSTR]
    get_drive_type.restype = wintypes.UINT
    return int(get_drive_type(f"{drive}:\\"))


def _mapped_drive_unc_root(drive: str) -> str:
    """Resolve a mapped drive to its UNC share root in the current logon context."""
    from ctypes import wintypes

    mpr = ctypes.WinDLL("mpr", use_last_error=True)
    get_connection = mpr.WNetGetConnectionW
    get_connection.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    get_connection.restype = wintypes.DWORD
    buffer = ctypes.create_unicode_buffer(32768)
    size = wintypes.DWORD(len(buffer))
    result = int(get_connection(f"{drive}:", buffer, ctypes.byref(size)))
    remote_root = buffer.value
    if result != 0 or not _is_unc_path(PureWindowsPath(remote_root)):
        raise ValueError(
            f"Cannot resolve mapped network drive '{drive}:' to a UNC path. "
            "Use the UNC path (for example, \\\\server\\share\\folder) instead."
        )
    return remote_root


def _normalize_mapped_drive(path: PureWindowsPath) -> str:
    """Replace a mapped network drive prefix with its stable UNC share path."""
    try:
        unc_root = PureWindowsPath(_mapped_drive_unc_root(path.drive[0]))
    except (AttributeError, OSError) as error:
        raise ValueError(
            f"Cannot resolve mapped network drive '{path.drive}' to a UNC path. "
            "Use the UNC path directly."
        ) from error
    drive_root = PureWindowsPath(f"{path.drive}\\")
    suffix = path.relative_to(drive_root)
    return unc_root.joinpath(*suffix.parts).as_posix()


def normalize_original_path(value: str, *, allow_relative: bool = True) -> str:
    """Return an absolute, lexically normalized path without following symlinks.

    Newly supplied relative paths are anchored to the current working directory.
    Serialized or subsequently mutated values can require an explicit root by
    setting ``allow_relative=False``. On Windows mapped network drives are
    stored as UNC paths so the association does not depend on a drive letter.
    """
    if not isinstance(value, str):
        raise TypeError("Snapshot directory original_path must be a string.")
    if not value or "\x00" in value:
        raise ValueError("Snapshot directory original_path must be a non-empty path without NUL characters.")

    windows_path = PureWindowsPath(value)
    if windows_path.drive and not windows_path.root:
        raise ValueError(f"Drive-relative paths are not supported: {value!r}.")

    if windows_path.is_absolute():
        if os.name == "nt" and not _is_unc_path(windows_path) and _windows_drive_type(windows_path.drive[0]) == 4:
            return _normalize_mapped_drive(windows_path)
        return windows_path.as_posix()

    posix_path = PurePosixPath(value)
    if posix_path.is_absolute():
        return posix_path.as_posix()

    if not allow_relative:
        raise ValueError(
            f"Snapshot directory original_path must be absolute; relative path {value!r} "
            "cannot be resolved safely."
        )

    # Anchor without resolving links or collapsing ``..`` across a symlink.
    return (Path.cwd() / Path(value)).as_posix()
