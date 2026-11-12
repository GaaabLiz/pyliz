import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QSettings

from pylizlib.qt.domain.config import QtConfigItem
from pylizlib.qt.handler.config import ConfigQtHandler


class ConfigQtHandlerTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="pyliz_qt_conf_")
        self.conf_path = Path(self.temp_dir.name) / "test_settings.ini"
        self.settings = QSettings(str(self.conf_path), QSettings.Format.IniFormat)

    def tearDown(self):
        self.settings.clear()
        self.settings.sync()
        self.temp_dir.cleanup()

    def test_write_and_read_string(self):
        item = QtConfigItem(id="app/theme", type=str, default="dark")
        ConfigQtHandler.qt_write(item, "light", self.settings)

        val = ConfigQtHandler.qt_read(item, self.settings)
        self.assertEqual(val, "light")

    def test_read_with_default_if_none(self):
        item = QtConfigItem(id="app/missing_key", type=str, default="default_val")
        val = ConfigQtHandler.qt_read(item, self.settings, return_default_if_none=True)
        self.assertEqual(val, "default_val")

    def test_write_list_with_max_size_and_deduplication(self):
        item = QtConfigItem(id="history/recent_files", type=list, default=[], max_list_size=3)

        ConfigQtHandler.qt_write(item, "file1.png", self.settings)
        ConfigQtHandler.qt_write(item, "file2.png", self.settings)
        ConfigQtHandler.qt_write(item, "file3.png", self.settings)
        # Adding file1 again should move it to the front without duplicating
        ConfigQtHandler.qt_write(item, "file1.png", self.settings)
        # Adding file4 should truncate list to max_list_size (3)
        ConfigQtHandler.qt_write(item, "file4.png", self.settings)

        res = ConfigQtHandler.qt_read(item, self.settings)
        self.assertEqual(len(res), 3)
        self.assertEqual(res[0], "file4.png")
        self.assertEqual(res[1], "file1.png")

    def test_write_list_missing_max_size_raises_assertion(self):
        item = QtConfigItem(id="invalid/list", type=list, default=[])
        with self.assertRaises(AssertionError):
            ConfigQtHandler.qt_write(item, "val", self.settings)

    def test_clear_all_and_file_path(self):
        item = QtConfigItem(id="key", type=str, default="")
        ConfigQtHandler.qt_write(item, "val", self.settings)
        ConfigQtHandler.qt_clear_all(self.settings)

        self.assertFalse(self.settings.contains("key"))
        file_path = ConfigQtHandler.get_qt_file_path(self.settings)
        self.assertTrue(file_path.endswith("test_settings.ini"))


if __name__ == "__main__":
    unittest.main()
