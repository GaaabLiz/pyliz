"""Windows process and service inspection helpers."""

import os
from pathlib import Path

import psutil

from pylizlib.core.os.system import is_os_windows


class WindowsOsUtils:
    """Inspect running Windows processes, executables, and services."""

    @staticmethod
    def is_exe_running(exe_path: Path) -> bool:
        """Check whether a process is running from the given executable.

        Args:
            exe_path (Path): Executable path to compare with running processes.

        Returns:
            bool: Whether a matching process is present.
        """
        exe_path_str = os.path.abspath(exe_path.__str__())  # normalize
        for proc in psutil.process_iter(["exe", "name"]):
            try:
                if proc.info["exe"] and os.path.abspath(proc.info["exe"]) == exe_path_str:
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return False

    @staticmethod
    def get_windows_exe_version(exe_path: Path) -> str:
        """Read the product version of a Windows executable.

        Args:
            exe_path (Path): Executable whose version resource should be read.

        Returns:
            str: Product version, or ``"N/A"`` when unavailable or on another OS.
        """
        if not is_os_windows():
            return "N/A"
        import win32api

        try:
            lang, codepage = win32api.GetFileVersionInfo(exe_path.__str__(), "\\VarFileInfo\\Translation")[0]
            str_info_path = f"\\StringFileInfo\\{lang:04X}{codepage:04X}\\ProductVersion"
            version = win32api.GetFileVersionInfo(exe_path.__str__(), str_info_path)
            return version
        except Exception:
            return "N/A"

    def get_service_executable_path(service_name: str) -> str | None:
        """Find the executable path configured for a Windows service.

        Args:
            service_name (str): Windows service name.

        Returns:
            str | None: Executable path, or None if unavailable or not on Windows.
        """
        if not is_os_windows():
            return None
        import winreg

        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                rf"SYSTEM\CurrentControlSet\Services\{service_name}",
            )
            image_path, _ = winreg.QueryValueEx(key, "ImagePath")
            winreg.CloseKey(key)

            # Rimuove eventuali argomenti e prende solo il percorso
            image_path = image_path.strip()
            if image_path.startswith('"'):
                image_path = image_path.split('"')[1]
            else:
                parts = image_path.split(" ")

                exe_parts = []
                for part in parts:
                    exe_parts.append(part)
                    if part.lower().endswith(".exe"):
                        break
                image_path = " ".join(exe_parts)
            return image_path
        except Exception:
            return None

    def is_service_running(service_name: str) -> bool:
        """Check whether a Windows service is running.

        Args:
            service_name (str): Windows service name.

        Returns:
            bool: Whether the service status reports running.
        """
        import win32service
        import win32serviceutil

        try:
            status = win32serviceutil.QueryServiceStatus(service_name)[1]
            return status == win32service.SERVICE_RUNNING
        except Exception:
            return False

    def get_service_version(service_name: str) -> str | None:
        """Read the file version of a Windows service executable.

        Args:
            service_name (str): Windows service name.

        Returns:
            str | None: Version string, or None when the service path is unavailable.
        """
        import win32api

        path = WindowsOsUtils.get_service_executable_path(service_name)
        if path is None:
            return None
        try:
            info = win32api.GetFileVersionInfo(path, "\\")
            ms = info["FileVersionMS"]
            ls = info["FileVersionLS"]
            version = f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"
            return version
        except Exception:
            return "N/A"
