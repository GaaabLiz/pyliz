import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMenu, QMenuBar, QWidget  # noqa: E402

from pylizlib.qt.domain.menuActionTool import ToolbarItem  # noqa: E402
from pylizlib.qt.domain.theme import AppTheme  # noqa: E402
from pylizlib.qt.handler.menuAction import MenuMasterHandler  # noqa: E402
from pylizlib.qt.handler.menuActionToolbar import ToolbarHandler  # noqa: E402


class MenuMasterToolbarOptionalTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_handler(self, toolbar_handler=None):
        return MenuMasterHandler(QMenu(), QMenuBar(), QWidget(), AppTheme(), toolbar_handler)

    def test_toolbar_methods_handle_absent_handler_and_repeated_clear(self):
        handler = self.make_handler()

        with patch("pylizlib.qt.handler.menuAction.logger.error") as log_error:
            handler.install_toolbar()
            handler.uninstall_toolbar()
            handler.clear_toolbar_handler()
            handler.clear_toolbar_handler()

        self.assertEqual(log_error.call_count, 4)
        self.assertIsNone(handler.toolbar_handler)

    def test_configured_but_uncreated_toolbar_can_be_uninstalled(self):
        toolbar_handler = ToolbarHandler(ToolbarItem("main", "Main", 24))
        handler = self.make_handler(toolbar_handler)

        handler.uninstall_toolbar()

        self.assertFalse(handler.toolbar_installed)
        self.assertFalse(toolbar_handler.is_created())


if __name__ == "__main__":
    unittest.main()
