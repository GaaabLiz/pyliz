import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QMenu,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

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


class ToolbarHandlerLifecycleTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_create_and_destroy_in_layout(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        handler = ToolbarHandler(ToolbarItem("custom", "Custom", 24), enable_logs=True)
        handler.create(widget, layout=layout)

        self.assertTrue(handler.is_created())
        self.assertEqual(layout.count(), 1)

        handler.destroy(widget, layout=layout)
        self.assertFalse(handler.is_created())
        self.assertIsNone(handler.toolbar)

    def test_uncreated_toolbar_methods_safe_handling(self):
        handler = ToolbarHandler(ToolbarItem("uncreated", "Uncreated", 24))
        widget = QWidget()

        # None of these should raise exceptions
        handler.destroy(widget)
        handler.add_action(QAction())
        handler.add_separator()
        self.assertIsNone(handler.add_action_button(QPushButton()))
        handler.remove_action_button(QPushButton(), QAction())
        handler.add_button_dropdown(QToolButton())
        handler.remove_button_dropdown(QToolButton())

    def test_dropdown_and_separator_when_created(self):
        window = QMainWindow()
        handler = ToolbarHandler(ToolbarItem("tb", "TB", 24), enable_logs=True)
        handler.create(window)

        handler.add_separator()
        btn = QToolButton()
        menu = QMenu(btn)
        btn.setMenu(menu)

        handler.add_button_dropdown(btn)
        self.assertEqual(len(handler.toolbar.actions()), 2)

        handler.remove_button_dropdown(btn)
        self.assertEqual(len(handler.toolbar.actions()), 1)


if __name__ == "__main__":
    unittest.main()
