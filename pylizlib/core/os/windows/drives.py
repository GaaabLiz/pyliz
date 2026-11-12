"""Native drive classification and mapped-share lookup for Windows."""

import ctypes
from pathlib import PureWindowsPath


def is_unc_path(path: PureWindowsPath) -> bool:
    """Identify a Windows UNC drive prefix without querying the operating system.

    Args:
        path (PureWindowsPath): Windows-flavoured lexical path, on any host.

    Returns:
        bool: Whether the drive prefix begins with a UNC server/share marker.
    """
    return path.drive.startswith("\\\\")


def get_drive_type(drive: str) -> int:
    """Query the native drive type in the current Windows logon context.

    Args:
        drive (str): Drive letter without colon, for example ``Z``.

    Returns:
        int: Native GetDriveTypeW value; 4 denotes a remote drive.

    Raises:
        OSError: If the native library cannot be loaded.
        AttributeError: If the platform does not expose the Windows binding.
    """
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_drive_type = kernel32.GetDriveTypeW
    get_drive_type.argtypes = [wintypes.LPCWSTR]
    get_drive_type.restype = wintypes.UINT
    return int(get_drive_type(f"{drive}:\\"))


def get_mapped_drive_unc_root(drive: str) -> str:
    """Resolve a mapped drive to its UNC root in the current logon context.

    Args:
        drive (str): Mapped drive letter without colon.

    Returns:
        str: UNC server/share root returned by WNetGetConnectionW.

    Raises:
        ValueError: If the mapping is unavailable or its response is not UNC.
        OSError: If loading the native library fails.
        AttributeError: If Windows bindings are unavailable on this host.
    """
    from ctypes import wintypes

    mpr = ctypes.WinDLL("mpr", use_last_error=True)
    get_connection = mpr.WNetGetConnectionW
    get_connection.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    get_connection.restype = wintypes.DWORD
    buffer = ctypes.create_unicode_buffer(32768)
    size = wintypes.DWORD(len(buffer))
    result = int(get_connection(f"{drive}:", buffer, ctypes.byref(size)))
    remote_root = buffer.value
    if result != 0 or not is_unc_path(PureWindowsPath(remote_root)):
        raise ValueError(f"Cannot resolve mapped network drive '{drive}:' to a UNC path. Use the UNC path (for example, \\\\server\\share\\folder) instead.")
    return remote_root
