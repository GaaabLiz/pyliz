import unittest
from unittest.mock import patch, MagicMock

from pylizlib.core.os.ui import (
    is_macos_dark_theme,
    is_dark_theme,
)


class IsMacosDarkThemeTestCase(unittest.TestCase):

    @patch("pylizlib.core.os.ui.subprocess.run")
    def test_dark_theme_detected(self, mock_run):
        mock_run.return_value = MagicMock(stdout="Dark\n")
        self.assertTrue(is_macos_dark_theme())

    @patch("pylizlib.core.os.ui.subprocess.run")
    def test_light_theme_detected(self, mock_run):
        mock_run.return_value = MagicMock(stdout="Light\n")
        self.assertFalse(is_macos_dark_theme())

    @patch("pylizlib.core.os.ui.subprocess.run", side_effect=Exception("fail"))
    def test_exception_returns_false(self, mock_run):
        self.assertFalse(is_macos_dark_theme())


class IsDarkThemeTestCase(unittest.TestCase):

    @patch("pylizlib.core.os.ui.is_macos_dark_theme", return_value=True)
    @patch("platform.system", return_value="Darwin")
    def test_macos_dark(self, mock_sys, mock_mac):
        self.assertTrue(is_dark_theme())

    @patch("pylizlib.core.os.ui.is_macos_dark_theme", return_value=False)
    @patch("platform.system", return_value="Darwin")
    def test_macos_light(self, mock_sys, mock_mac):
        self.assertFalse(is_dark_theme())

    @patch("platform.system", return_value="Linux")
    def test_unsupported_os_raises(self, mock_sys):
        with self.assertRaises(Exception):
            is_dark_theme()


if __name__ == "__main__":
    unittest.main()
