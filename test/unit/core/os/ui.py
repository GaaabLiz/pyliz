import unittest
from unittest.mock import MagicMock, patch

from pylizlib.core.os.ui import (
    is_dark_theme,
    is_macos_dark_theme,
    is_windows_dark_theme,
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

    @patch("pylizlib.core.os.ui.is_windows_dark_theme", return_value=True)
    @patch("platform.system", return_value="Windows")
    def test_windows_delegation(self, mock_sys, mock_win):
        self.assertTrue(is_dark_theme())


class IsWindowsDarkThemeTestCase(unittest.TestCase):
    @patch("platform.system", return_value="Linux")
    def test_non_windows_returns_false(self, mock_sys):
        self.assertFalse(is_windows_dark_theme())

    @patch("platform.system", return_value="Windows")
    def test_windows_dark_true(self, mock_sys):
        mock_winreg = MagicMock()
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value = mock_key
        mock_winreg.QueryValueEx.return_value = (0, 1)  # 0 = dark
        with patch.dict("sys.modules", {"winreg": mock_winreg}):
            self.assertTrue(is_windows_dark_theme())

    @patch("platform.system", return_value="Windows")
    def test_windows_dark_false(self, mock_sys):
        mock_winreg = MagicMock()
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value = mock_key
        mock_winreg.QueryValueEx.return_value = (1, 1)  # 1 = light
        with patch.dict("sys.modules", {"winreg": mock_winreg}):
            self.assertFalse(is_windows_dark_theme())

    @patch("platform.system", return_value="Windows")
    def test_windows_exception_returns_false(self, mock_sys):
        mock_winreg = MagicMock()
        mock_winreg.OpenKey.side_effect = Exception("Registry error")
        with patch.dict("sys.modules", {"winreg": mock_winreg}):
            self.assertFalse(is_windows_dark_theme())


if __name__ == "__main__":
    unittest.main()
