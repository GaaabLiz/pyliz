import getpass
import os
import platform
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pylizlib.core.os.utils import (
    get_folder_size_mb,
    get_directory_size,
    has_disk_free_space,
    get_free_space_mb,
    check_move_dirs_free_space,
    is_command_available,
    is_os_unix,
    is_os_windows,
    is_software_installed,
    get_system_username,
    open_system_folder,
)


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


class CheckMoveDirsFreeSpaceTestCase(unittest.TestCase):

    def test_small_source_large_dest(self):
        with tempfile.TemporaryDirectory() as src, tempfile.TemporaryDirectory() as dst:
            self.assertTrue(check_move_dirs_free_space(src, dst))


class IsCommandAvailableTestCase(unittest.TestCase):

    def test_known_command(self):
        self.assertTrue(is_command_available("ls"))

    def test_unknown_command(self):
        self.assertFalse(is_command_available("__nonexistent_command_xyz__"))


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


class OpenSystemFolderTestCase(unittest.TestCase):

    @patch("pylizlib.core.os.utils.subprocess.Popen")
    def test_opens_existing_folder(self, mock_popen):
        with tempfile.TemporaryDirectory() as td:
            open_system_folder(td)
            mock_popen.assert_called_once()

    def test_non_existing_folder_raises(self):
        with self.assertRaises(FileNotFoundError):
            open_system_folder("/non/existing/folder/xyz")


if __name__ == "__main__":
    unittest.main()
