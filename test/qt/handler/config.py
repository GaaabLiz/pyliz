import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QSettings

from pylizlib.qt.domain.config import QtConfigItem
from pylizlib.qt.handler.config import ConfigQtHandler


class ConfigQtHandlerTestCase(unittest.TestCase):
    def test_scalar_values_survive_reopening_settings(self):
        values = (("enabled", bool, True), ("retries", int, 4), ("scale", float, 1.5))
        with tempfile.TemporaryDirectory() as temp_dir:
            settings_path = Path(temp_dir) / "settings.ini"
            setting = QSettings(str(settings_path), QSettings.Format.IniFormat)

            for item_id, value_type, value in values:
                item = QtConfigItem(item_id, value_type, value_type())
                ConfigQtHandler.qt_write(item, value, setting)

            reopened = QSettings(str(settings_path), QSettings.Format.IniFormat)
            for item_id, value_type, expected in values:
                with self.subTest(item=item_id):
                    self.assertEqual(ConfigQtHandler.qt_read(QtConfigItem(item_id, value_type, None), reopened), expected)

    def test_unsupported_type_is_reported(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            setting = QSettings(str(Path(temp_dir) / "settings.ini"), QSettings.Format.IniFormat)

            with self.assertRaisesRegex(TypeError, "Unsupported Qt setting type"):
                ConfigQtHandler.qt_write(QtConfigItem("unsupported", tuple, ()), (), setting)

    def test_str_value_roundtrip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings_path = Path(temp_dir) / "settings.ini"
            setting = QSettings(str(settings_path), QSettings.Format.IniFormat)
            item = QtConfigItem("username", str, "guest")

            ConfigQtHandler.qt_write(item, "admin", setting)
            reopened = QSettings(str(settings_path), QSettings.Format.IniFormat)
            self.assertEqual(ConfigQtHandler.qt_read(item, reopened), "admin")

    def test_list_value_requires_max_list_size(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            setting = QSettings(str(Path(temp_dir) / "settings.ini"), QSettings.Format.IniFormat)
            item = QtConfigItem("history", list, [], max_list_size=None)

            with self.assertRaisesRegex(AssertionError, "max_list_size must be set"):
                ConfigQtHandler.qt_write(item, "entry", setting)

    def test_list_value_deduplicates_and_clamps(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings_path = Path(temp_dir) / "settings.ini"
            setting = QSettings(str(settings_path), QSettings.Format.IniFormat)
            item = QtConfigItem("recents", list, [], max_list_size=3)

            ConfigQtHandler.qt_write(item, "a", setting)
            ConfigQtHandler.qt_write(item, "b", setting)
            ConfigQtHandler.qt_write(item, "a", setting)  # "a" moves to front: ["a", "b"]
            ConfigQtHandler.qt_write(item, "c", setting)  # ["c", "a", "b"]
            ConfigQtHandler.qt_write(item, "d", setting)  # ["d", "c", "a"] (max size 3)

            result = ConfigQtHandler.qt_read(item, setting)
            self.assertEqual(result, ["d", "c", "a"])

    def test_qt_read_default_when_none(self):
        from unittest.mock import MagicMock

        setting = MagicMock()
        setting.value.return_value = None
        item = QtConfigItem("missing", str, "default_val")

        self.assertIsNone(ConfigQtHandler.qt_read(item, setting, return_default_if_none=False))
        self.assertEqual(ConfigQtHandler.qt_read(item, setting, return_default_if_none=True), "default_val")

    def test_qt_clear_all_and_file_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings_path = Path(temp_dir) / "settings.ini"
            setting = QSettings(str(settings_path), QSettings.Format.IniFormat)
            item = QtConfigItem("key", str, "")

            ConfigQtHandler.qt_write(item, "val", setting)
            self.assertEqual(ConfigQtHandler.get_qt_file_path(setting), str(settings_path))
            self.assertIn("key", setting.allKeys())

            ConfigQtHandler.qt_clear_all(setting)
            self.assertEqual(setting.allKeys(), [])


if __name__ == "__main__":
    unittest.main()
