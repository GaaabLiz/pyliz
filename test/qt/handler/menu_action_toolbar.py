import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton  # noqa: E402

from pylizlib.qt.domain.menuActionTool import (  # noqa: E402
    ActionGroupItem,
    ActionItem,
    InstanceData,
    InstanceInstallSetting,
    ToolbarItem,
    ToolbarWidgetType,
)
from pylizlib.qt.handler.menuActionInst import InstanceAction, InstanceActionGroup  # noqa: E402
from pylizlib.qt.handler.menuActionToolbar import ToolbarHandler  # noqa: E402


class MenuActionToolbarButtonTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_toolbar(self):
        window = QMainWindow()
        toolbar = ToolbarHandler(ToolbarItem("main", "Main", 24))
        toolbar.create(window)
        settings = InstanceInstallSetting(
            menu_add=False,
            toolbar_add=True,
            toolbar_widget_type=ToolbarWidgetType.BUTTON,
        )
        return window, toolbar, InstanceData(settings=settings)

    def test_single_action_button_installs_triggers_removes_and_reinstalls(self):
        window, toolbar, data = self.make_toolbar()
        triggered = []
        action = InstanceAction(
            window,
            ActionItem("open", "Open"),
            callback=lambda: triggered.append("open"),
            data=data,
        )

        action.toolbar_install(toolbar)
        self.assertEqual(len(toolbar.toolbar.actions()), 1)
        button = toolbar.toolbar.widgetForAction(toolbar.toolbar.actions()[0])
        self.assertIsInstance(button, QPushButton)
        button.click()
        self.assertEqual(triggered, ["open"])

        action.toolbar_uninstall(toolbar)
        self.assertEqual(toolbar.toolbar.actions(), [])
        action.toolbar_install(toolbar)
        self.assertEqual(len(toolbar.toolbar.actions()), 1)
        action.toolbar_uninstall(toolbar)
        self.assertEqual(toolbar.toolbar.actions(), [])

    def test_action_group_buttons_install_and_remove_as_a_unit(self):
        window, toolbar, data = self.make_toolbar()
        action_group = InstanceActionGroup(
            window,
            ActionGroupItem(
                "tools",
                [ActionItem("one", "One"), ActionItem("two", "Two")],
            ),
            data=data,
        )

        action_group.toolbar_install(toolbar)
        self.assertEqual(len(toolbar.toolbar.actions()), 2)
        for widget_action in toolbar.toolbar.actions():
            self.assertIsInstance(toolbar.toolbar.widgetForAction(widget_action), QPushButton)

        action_group.toolbar_uninstall(toolbar)
        self.assertEqual(toolbar.toolbar.actions(), [])
        action_group.toolbar_install(toolbar)
        self.assertEqual(len(toolbar.toolbar.actions()), 2)
        action_group.toolbar_uninstall(toolbar)
        self.assertEqual(toolbar.toolbar.actions(), [])


if __name__ == "__main__":
    unittest.main()
