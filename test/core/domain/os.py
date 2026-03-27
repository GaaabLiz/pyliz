import unittest

from pylizlib.core.domain.os import FileOsType, FileType, OsTheme, OsType


class OsDomainTestCase(unittest.TestCase):

    def test_os_type_values(self):
        self.assertEqual(OsType.WINDOWS.value, "windows")
        self.assertEqual(OsType.UNKNOWN.value, "unknown")

    def test_os_theme_values(self):
        self.assertEqual(OsTheme.LIGHT.value, "light")
        self.assertEqual(OsTheme.DARK.value, "dark")

    def test_file_os_type_values(self):
        self.assertEqual(FileOsType.DIRECTORY.value, "Directory")
        self.assertEqual(FileOsType.FILE.value, "File")

    def test_file_type_core_values(self):
        self.assertEqual(FileType.ANY.value, "ANY")
        self.assertEqual(FileType.IMAGE.value, "IMAGE")
        self.assertEqual(FileType.VIDEO.value, "VIDEO")
        self.assertEqual(FileType.UNKNOWN.value, "UNKNOWN")


if __name__ == "__main__":
    unittest.main()