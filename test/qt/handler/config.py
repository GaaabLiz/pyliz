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


if __name__ == "__main__":
    unittest.main()
