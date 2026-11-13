"""Compatibility exports for legacy cross-platform OS helpers.

New code should import from the focused ``paths``, ``filesystem``, ``commands``,
``system`` and ``windows`` modules. This module preserves the historical import paths.
"""

from pylizlib.core.os.commands import is_command_available, is_command_available_with_run, is_software_installed
from pylizlib.core.os.filesystem.capacity import (
    check_move_dirs_free_space,
    get_directory_size,
    get_folder_size_mb,
    get_free_space_mb,
    has_disk_free_space,
)
from pylizlib.core.os.paths.safety import is_critical_system_path
from pylizlib.core.os.system import get_system_username, is_os_unix, is_os_windows, open_system_folder
from pylizlib.core.os.windows.commands import PATH_DEFAULT_GIT_BASH
from pylizlib.core.os.windows.processes import WindowsOsUtils

__all__ = [
    "PATH_DEFAULT_GIT_BASH",
    "WindowsOsUtils",
    "check_move_dirs_free_space",
    "get_directory_size",
    "get_folder_size_mb",
    "get_free_space_mb",
    "get_system_username",
    "has_disk_free_space",
    "is_command_available",
    "is_command_available_with_run",
    "is_critical_system_path",
    "is_os_unix",
    "is_os_windows",
    "is_software_installed",
    "open_system_folder",
]
