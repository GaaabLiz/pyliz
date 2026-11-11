import getpass
import os
import platform
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import psutil

from pylizlib.core.os.utils import (
    WindowsOsUtils,
    check_move_dirs_free_space,
    get_directory_size,
    get_folder_size_mb,
    get_free_space_mb,
    get_system_username,
    has_disk_free_space,
    is_command_available,
    is_command_available_with_run,
    is_critical_system_path,
    is_os_unix,
    is_os_windows,
    is_software_installed,
    open_system_folder,
)


class IsCriticalSystemPathTestCase(unittest.TestCase):
    def test_root_is_critical(self):
        self.assertTrue(is_critical_system_path("/"))

    def test_home_is_critical(self):
        self.assertTrue(is_critical_system_path(Path.home()))

    def test_usr_bin_is_critical(self):
        self.assertTrue(is_critical_system_path("/usr/bin/test"))
        self.assertTrue(is_critical_system_path("/usr"))

    def test_regular_path_is_not_critical(self):
        self.assertFalse(is_critical_system_path(Path.home() / "Documents" / "MyProject"))
        self.assertFalse(is_critical_system_path("/tmp/test_dir"))

    def test_path_resolve_exception_returns_true(self):
        with patch.object(Path, "resolve", side_effect=RuntimeError("resolve error")):
            self.assertTrue(is_critical_system_path("/some/path"))

    def test_windows_critical_paths(self):
        critical_dir = Path("/mock/windows")
        with patch("pylizlib.core.os.utils.sys.platform", "win32"):
            with patch.dict(os.environ, {"windir": str(critical_dir), "ProgramFiles": "/mock/programs"}):
                self.assertTrue(is_critical_system_path(critical_dir / "System32"))
                self.assertTrue(is_critical_system_path("/mock/programs/App"))
                self.assertFalse(is_critical_system_path("/mock/other/folder"))

    def test_relative_to_value_error_fails_closed(self):
        with patch.object(Path, "is_relative_to", side_effect=ValueError("different drive")):
            self.assertTrue(is_critical_system_path("/non/critical/path"))

    def test_path_resolution_failure_is_treated_as_critical(self):
        with patch.object(Path, "resolve", side_effect=OSError("cannot resolve path")):
            self.assertTrue(is_critical_system_path("/tmp/unverified"))

    def test_invalid_path_returns_false(self):
        with patch.object(Path, "resolve", side_effect=ValueError("Invalid path")):
            self.assertFalse(is_critical_system_path("/any/path"))


class GetFolderSizeMbTestCase(unittest.TestCase):
    def test_known_size(self):
        with tempfile.TemporaryDirectory() as td:
            data = b"x" * (1024 * 1024)
            with open(os.path.join(td, "1mb.bin"), "wb") as f:
                f.write(data)
            size = get_folder_size_mb(td)
            self.assertAlmostEqual(size, 1.0, places=1)

    def test_empty_folder(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(get_folder_size_mb(td), 0.0)


class GetDirectorySizeTestCase(unittest.TestCase):
    def test_known_size(self):
        with tempfile.TemporaryDirectory() as td:
            data = b"y" * (512 * 1024)
            with open(os.path.join(td, "half.bin"), "wb") as f:
                f.write(data)
            size = get_directory_size(td)
            self.assertAlmostEqual(size, 0.5, places=1)


class HasDiskFreeSpaceTestCase(unittest.TestCase):
    def test_has_enough_space(self):
        self.assertTrue(has_disk_free_space(tempfile.gettempdir(), 1))

    def test_unreasonable_amount(self):
        self.assertFalse(has_disk_free_space(tempfile.gettempdir(), 999_999_999))


class GetFreeSpaceMbTestCase(unittest.TestCase):
    def test_returns_positive(self):
        free = get_free_space_mb(tempfile.gettempdir())
        self.assertGreater(free, 0)

    @patch("pylizlib.core.os.utils.shutil.disk_usage")
    def test_uses_cross_platform_disk_usage_in_megabytes(self, mock_disk_usage):
        mock_disk_usage.return_value.free = 5 * 1024 * 1024

        free = get_free_space_mb("C:/")

        self.assertEqual(free, 5.0)
        mock_disk_usage.assert_called_once_with("C:/")

    @patch("pylizlib.core.os.utils.shutil.disk_usage", side_effect=PermissionError("volume denied"))
    def test_preserves_volume_access_errors(self, _mock_disk_usage):
        with self.assertRaisesRegex(PermissionError, "volume denied"):
            get_free_space_mb("C:/")


class CheckMoveDirsFreeSpaceTestCase(unittest.TestCase):
    def test_small_source_large_dest(self):
        with tempfile.TemporaryDirectory() as src, tempfile.TemporaryDirectory() as dst:
            self.assertTrue(check_move_dirs_free_space(src, dst))


class IsCommandAvailableTestCase(unittest.TestCase):
    def test_known_command(self):
        self.assertTrue(is_command_available("ls"))

    def test_unknown_command(self):
        self.assertFalse(is_command_available("__nonexistent_command_xyz__"))

    def test_availability_check_does_not_execute_program(self):
        with tempfile.TemporaryDirectory() as td:
            marker = Path(td) / "executed.txt"
            command = Path(td) / "dangerous-command"
            command.write_text(f"#!/bin/sh\nprintf executed > '{marker}'\nexit 2\n", encoding="utf-8")
            command.chmod(0o755)

            with patch.dict(os.environ, {"PATH": td}):
                self.assertTrue(is_command_available_with_run(command.name))

            self.assertFalse(marker.exists())


class IsOsTestCase(unittest.TestCase):
    def test_is_os_unix(self):
        current = platform.system()
        if current in ("Linux", "Darwin"):
            self.assertTrue(is_os_unix())
        else:
            self.assertFalse(is_os_unix())

    def test_is_os_windows(self):
        current = platform.system()
        if current == "Windows":
            self.assertTrue(is_os_windows())
        else:
            self.assertFalse(is_os_windows())

    def test_mutual_exclusivity_on_current_os(self):
        self.assertTrue(is_os_unix() or is_os_windows())


class GetSystemUsernameTestCase(unittest.TestCase):
    def test_matches_getpass(self):
        self.assertEqual(get_system_username(), getpass.getuser())


class IsSoftwareInstalledTestCase(unittest.TestCase):
    def test_executable_file(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".sh") as tmp:
            tmp_name = tmp.name
        try:
            os.chmod(tmp_name, os.stat(tmp_name).st_mode | stat.S_IEXEC)
            self.assertTrue(is_software_installed(Path(tmp_name)))
        finally:
            os.unlink(tmp_name)

    def test_non_executable_file(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as tmp:
            tmp_name = tmp.name
        try:
            os.chmod(tmp_name, stat.S_IRUSR | stat.S_IWUSR)
            self.assertFalse(is_software_installed(Path(tmp_name)))
        finally:
            os.unlink(tmp_name)

    def test_non_existing_path(self):
        self.assertFalse(is_software_installed(Path("/non/existing/binary")))


class IsCommandAvailableWithRunTestCase(unittest.TestCase):
    @patch("pylizlib.core.os.utils.subprocess.run")
    @patch("pylizlib.core.os.utils.shutil.which", return_value="/usr/bin/git")
    def test_available(self, mock_which, mock_run):
        self.assertTrue(is_command_available_with_run("git"))
        mock_which.assert_called_once_with("git")
        mock_run.assert_not_called()

    @patch("pylizlib.core.os.utils.shutil.which", return_value=None)
    def test_not_available(self, mock_which):
        self.assertFalse(is_command_available_with_run("nonexistent_cmd"))
        mock_which.assert_called_once_with("nonexistent_cmd")


class OpenSystemFolderTestCase(unittest.TestCase):
    @patch("pylizlib.core.os.utils.subprocess.Popen")
    def test_opens_existing_folder_darwin(self, mock_popen):
        with tempfile.TemporaryDirectory() as td:
            with patch("pylizlib.core.os.utils.sys.platform", "darwin"):
                open_system_folder(td)
                mock_popen.assert_called_once_with(["open", td])

    @patch("pylizlib.core.os.utils.subprocess.Popen")
    def test_opens_existing_folder_linux(self, mock_popen):
        with tempfile.TemporaryDirectory() as td:
            with patch("pylizlib.core.os.utils.sys.platform", "linux"):
                open_system_folder(td)
                mock_popen.assert_called_once_with(["xdg-open", td])

    def test_opens_existing_folder_windows_startfile(self):
        with tempfile.TemporaryDirectory() as td:
            with patch("pylizlib.core.os.utils.sys.platform", "win32"):
                with patch.object(os, "startfile", create=True) as mock_startfile:
                    open_system_folder(td)
                    mock_startfile.assert_called_once_with(td)

    @patch("pylizlib.core.os.utils.subprocess.Popen")
    def test_opens_existing_folder_windows_explorer(self, mock_popen):
        with tempfile.TemporaryDirectory() as td:
            with patch("pylizlib.core.os.utils.sys.platform", "win32"):
                with patch.object(os, "startfile", None, create=True):
                    # Remove startfile attribute so hasattr returns False
                    with patch("pylizlib.core.os.utils.os", spec=[s for s in dir(os) if s != "startfile"]):
                        open_system_folder(td)
                        mock_popen.assert_called_once_with(["explorer", td])

    def test_non_existing_folder_raises(self):
        with self.assertRaises(FileNotFoundError):
            open_system_folder("/non/existing/folder/xyz")


class WindowsOsUtilsTestCase(unittest.TestCase):
    @patch("pylizlib.core.os.utils.psutil.process_iter")
    def test_is_exe_running_found(self, mock_process_iter):
        target_path = Path("/app/bin/test.exe")
        mock_proc1 = MagicMock()
        mock_proc1.info = {"exe": "/other/proc.exe", "name": "other"}
        mock_proc2 = MagicMock()
        mock_proc2.info = {"exe": str(target_path), "name": "test"}
        mock_process_iter.return_value = [mock_proc1, mock_proc2]

        self.assertTrue(WindowsOsUtils.is_exe_running(target_path))

    @patch("pylizlib.core.os.utils.psutil.process_iter")
    def test_is_exe_running_not_found_and_exceptions(self, mock_process_iter):
        target_path = Path("/app/bin/test.exe")
        mock_proc_denied = MagicMock()
        type(mock_proc_denied).info = unittest.mock.PropertyMock(side_effect=psutil.AccessDenied(pid=1))
        mock_proc_no_such = MagicMock()
        type(mock_proc_no_such).info = unittest.mock.PropertyMock(side_effect=psutil.NoSuchProcess(pid=2))
        mock_proc_none = MagicMock()
        mock_proc_none.info = {"exe": None, "name": "system"}

        mock_process_iter.return_value = [mock_proc_denied, mock_proc_no_such, mock_proc_none]
        self.assertFalse(WindowsOsUtils.is_exe_running(target_path))

    def test_get_windows_exe_version_non_windows(self):
        with patch("pylizlib.core.os.utils.is_os_windows", return_value=False):
            self.assertEqual(WindowsOsUtils.get_windows_exe_version(Path("test.exe")), "N/A")

    def test_get_windows_exe_version_windows_success(self):
        mock_win32api = MagicMock()
        mock_win32api.GetFileVersionInfo.side_effect = [
            [(1033, 1200)],  # translation
            "1.2.3.4",  # product version
        ]
        with patch("pylizlib.core.os.utils.is_os_windows", return_value=True):
            with patch.dict(sys.modules, {"win32api": mock_win32api}):
                version = WindowsOsUtils.get_windows_exe_version(Path("test.exe"))
                self.assertEqual(version, "1.2.3.4")

    def test_get_windows_exe_version_windows_exception(self):
        mock_win32api = MagicMock()
        mock_win32api.GetFileVersionInfo.side_effect = RuntimeError("win32api error")
        with patch("pylizlib.core.os.utils.is_os_windows", return_value=True):
            with patch.dict(sys.modules, {"win32api": mock_win32api}):
                self.assertEqual(WindowsOsUtils.get_windows_exe_version(Path("test.exe")), "N/A")

    def test_get_service_executable_path_non_windows(self):
        with patch("pylizlib.core.os.utils.is_os_windows", return_value=False):
            self.assertIsNone(WindowsOsUtils.get_service_executable_path("AnyService"))

    def test_get_service_executable_path_quoted(self):
        mock_winreg = MagicMock()
        mock_winreg.OpenKey.return_value = MagicMock()
        mock_winreg.QueryValueEx.return_value = ('"C:\\Program Files\\App\\service.exe" /run', 1)
        with patch("pylizlib.core.os.utils.is_os_windows", return_value=True):
            with patch.dict(sys.modules, {"winreg": mock_winreg}):
                path = WindowsOsUtils.get_service_executable_path("TestService")
                self.assertEqual(path, "C:\\Program Files\\App\\service.exe")

    def test_get_service_executable_path_unquoted(self):
        mock_winreg = MagicMock()
        mock_winreg.OpenKey.return_value = MagicMock()
        mock_winreg.QueryValueEx.return_value = ("C:\\Program Files\\App\\service.exe -k run", 1)
        with patch("pylizlib.core.os.utils.is_os_windows", return_value=True):
            with patch.dict(sys.modules, {"winreg": mock_winreg}):
                path = WindowsOsUtils.get_service_executable_path("TestService")
                self.assertEqual(path, "C:\\Program Files\\App\\service.exe")

    def test_get_service_executable_path_exception(self):
        mock_winreg = MagicMock()
        mock_winreg.OpenKey.side_effect = OSError("service not found")
        with patch("pylizlib.core.os.utils.is_os_windows", return_value=True):
            with patch.dict(sys.modules, {"winreg": mock_winreg}):
                self.assertIsNone(WindowsOsUtils.get_service_executable_path("BadService"))

    def test_is_service_running_states(self):
        mock_service = MagicMock()
        mock_service.SERVICE_RUNNING = 4
        mock_util = MagicMock()
        mock_util.QueryServiceStatus.return_value = (0, 4)  # running

        with patch.dict(sys.modules, {"win32service": mock_service, "win32serviceutil": mock_util}):
            self.assertTrue(WindowsOsUtils.is_service_running("RunningService"))

            mock_util.QueryServiceStatus.return_value = (0, 1)  # stopped
            self.assertFalse(WindowsOsUtils.is_service_running("StoppedService"))

            mock_util.QueryServiceStatus.side_effect = RuntimeError("service error")
            self.assertFalse(WindowsOsUtils.is_service_running("ErrorService"))

    def test_get_service_version_modes(self):
        mock_win32api = MagicMock()
        mock_win32api.GetFileVersionInfo.return_value = {
            "FileVersionMS": (2 << 16) | 5,  # 2.5
            "FileVersionLS": (1 << 16) | 9,  # 1.9
        }
        with patch.dict(sys.modules, {"win32api": mock_win32api}):
            with patch.object(WindowsOsUtils, "get_service_executable_path", return_value=None):
                self.assertIsNone(WindowsOsUtils.get_service_version("NonExistentService"))

            with patch.object(WindowsOsUtils, "get_service_executable_path", return_value="C:\\srv.exe"):
                version = WindowsOsUtils.get_service_version("ValidService")
                self.assertEqual(version, "2.5.1.9")

                mock_win32api.GetFileVersionInfo.side_effect = RuntimeError("version error")
                self.assertEqual(WindowsOsUtils.get_service_version("ValidService"), "N/A")


if __name__ == "__main__":
    unittest.main()
