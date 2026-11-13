"""Windows metadata adapter, loading native APIs only when called."""

import shutil
from pathlib import Path


def copy_streams(source: Path, destination: Path) -> None:
    """Copy NTFS alternate data streams exposed by FindFirstStreamW.

    Args:
        source (Path): Source file or directory whose contents or metadata are read.
        destination (Path): Target path receiving the copied content or metadata.

    Returns:
        None: No return value.

    Raises:
        OSError: Stream enumeration or byte copying fails. Native errors 1, 38 and 50
            on the first enumeration mean this source exposes no supported streams.
        AttributeError: The host does not provide ctypes.WinDLL; call this only on Windows.

    Notes:
        The default unnamed data stream is excluded. Only named :$DATA streams
        are copied, and the native enumeration handle is closed in all cases.
    """
    import ctypes
    from ctypes import wintypes

    class FindStreamData(ctypes.Structure):
        """Win32 stream enumeration result layout.

        Attributes:
            stream_size (int): Native signed 64-bit stream byte count.
            stream_name (str): Native WCHAR[296] stream name including its type suffix.
        """

        _fields_ = [("stream_size", ctypes.c_longlong), ("stream_name", wintypes.WCHAR * 296)]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    find_first = kernel32.FindFirstStreamW
    find_first.argtypes = [wintypes.LPCWSTR, ctypes.c_int, ctypes.POINTER(FindStreamData), wintypes.DWORD]
    find_first.restype = wintypes.HANDLE
    find_next = kernel32.FindNextStreamW
    find_next.argtypes = [wintypes.HANDLE, ctypes.POINTER(FindStreamData)]
    find_next.restype = wintypes.BOOL
    find_close = kernel32.FindClose
    find_close.argtypes = [wintypes.HANDLE]
    find_close.restype = wintypes.BOOL

    stream_data = FindStreamData()
    handle = find_first(str(source), 0, ctypes.byref(stream_data), 0)
    invalid_handle = ctypes.c_void_p(-1).value
    if handle == invalid_handle:
        error_code = ctypes.get_last_error()

        # These filesystems expose no alternate data streams.
        if error_code in (1, 38, 50):
            return
        raise ctypes.WinError(error_code)

    try:
        while True:
            stream_name = stream_data.stream_name
            if stream_name != "::$DATA" and stream_name.endswith(":$DATA"):
                stream_suffix = stream_name[:-6]
                with open(f"{source}{stream_suffix}", "rb") as input_stream:
                    with open(f"{destination}{stream_suffix}", "wb") as output_stream:
                        shutil.copyfileobj(input_stream, output_stream)
            if not find_next(handle, ctypes.byref(stream_data)):
                error_code = ctypes.get_last_error()
                if error_code != 38:  # ERROR_HANDLE_EOF
                    raise ctypes.WinError(error_code)
                break
    finally:
        find_close(handle)
