import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

import pytest

pytest.importorskip("PySide6.QtGui")
pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QMainWindow,
    QMenu,
    QMenuBar,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from pylizlib.qt.domain.menuActionTool import (
    ActionGroupItem,
    ActionItem,
    InstanceData,
    InstanceInstallSetting,
    ToolbarItem,
    ToolbarWidgetType,
)
from pylizlib.qt.domain.theme import AppTheme
from pylizlib.qt.handler.menuAction import MenuMasterHandler
from pylizlib.qt.handler.menuActionInst import (
    InstanceActionGroup,
)
from pylizlib.qt.handler.menuActionToolbar import ToolbarHandler
from pylizlib.qt.util.menuActionTool import (
    create_action,
    create_action_btn_push,
    create_action_contextual,
    create_action_group,
    create_action_text_path,
    create_action_toggle_dock,
    create_menu_action_drop_button,
    create_toolbar,
)

os.environ["QT_QPA_PLATFORM"] = "offscreen"
app = QApplication.instance() or QApplication([])


class MenuActionDomainAndUtilsTestCase(unittest.TestCase):
    def setUp(self):
        self.theme = AppTheme()
        self.parent = QWidget()

    def test_action_group_item_get_action(self):
        a1 = ActionItem(id="act1", text="Action 1")
        a2 = ActionItem(id="act2", text="Action 2")
        group = ActionGroupItem(id="grp1", actions=[a1, a2])

        self.assertEqual(group.get_action_item("act1"), a1)
        self.assertEqual(group.get_action_item("act2"), a2)
        self.assertIsNone(group.get_action_item("nonexistent"))

    def test_instance_data_order_increment(self):
        inst1 = InstanceData()
        inst2 = InstanceData()
        self.assertTrue(inst2.order > inst1.order)

    def test_create_toolbar(self):
        t_item = ToolbarItem(id="tlb_main", name="Main Toolbar", icon_size=24, movable=False)
        toolbar = create_toolbar(t_item, self.parent)
        self.assertEqual(toolbar.objectName(), "tlb_main")
        self.assertEqual(toolbar.windowTitle(), "Main Toolbar")
        self.assertFalse(toolbar.isMovable())

    def test_create_action_variations(self):
        clicked = []
        item = ActionItem(
            id="act_save",
            text="Save",
            text_for_group="Save As Group",
            shortcut="Ctrl+S",
            enabled=True,
            checkable=True,
            checked=True,
            visible=True,
        )
        action = create_action(
            item,
            self.parent,
            self.theme,
            callback=lambda: clicked.append(True),
            use_text_for_group=False,
        )
        self.assertEqual(action.text(), "Save")
        self.assertTrue(action.isCheckable())
        self.assertTrue(action.isChecked())
        self.assertEqual(action.shortcut().toString(), "Ctrl+S")

        action.trigger()
        self.assertEqual(clicked, [True])

        action_group_text = create_action(item, self.parent, self.theme, use_text_for_group=True)
        self.assertEqual(action_group_text.text(), "Save As Group")

    def test_create_action_group(self):
        a1 = ActionItem(id="opt1", text="Option 1")
        a2 = ActionItem(id="opt2", text="Option 2")
        group_item = ActionGroupItem(id="grp", actions=[a1, a2], exclusive=True)

        triggered = []
        action_group = create_action_group(
            group_item,
            self.parent,
            self.theme,
            callback=lambda act: triggered.append(act.text()),
        )
        self.assertTrue(action_group.isExclusive())
        self.assertEqual(len(action_group.actions()), 2)

        action_group.actions()[0].trigger()
        self.assertEqual(triggered, ["Option 1"])

    def test_create_action_text_path(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory)
            clicked = []
            action = create_action_text_path(path, self.parent, on_clicked=lambda: clicked.append(True))
            self.assertEqual(action.text(), str(path))
            self.assertTrue(action.isEnabled())
            action.trigger()
            self.assertEqual(clicked, [True])

    def test_create_action_contextual(self):
        clicked = []
        act = create_action_contextual("Custom Action", self.parent, on_clicked=lambda: clicked.append(True))
        self.assertEqual(act.text(), "Custom Action")
        act.trigger()
        self.assertEqual(clicked, [True])

    def test_create_action_toggle_dock(self):
        dock = QDockWidget("My Dock")
        dock.setVisible(False)
        item = ActionItem(id="toggle_dock", text="View Dock", shortcut="F12")
        action = create_action_toggle_dock(item, dock)

        self.assertFalse(action.isChecked())
        action.setChecked(True)
        self.assertFalse(dock.isHidden())

        dock.setVisible(False)
        self.assertFalse(action.isChecked())

    def test_create_action_btn_push(self):
        item = ActionItem(id="btn_act", text="Push Me")
        action = QAction("Push Me", self.parent)
        triggered = []
        action.triggered.connect(lambda: triggered.append(True))

        btn = create_action_btn_push(item, action, self.parent)
        self.assertEqual(btn.text(), "Push Me")
        btn.click()
        self.assertEqual(triggered, [True])

    def test_create_menu_action_drop_button(self):
        menu = QMenu("Dropdown Menu", self.parent)
        menu.setObjectName("Dropdown Menu")
        btn = create_menu_action_drop_button(menu)
        self.assertEqual(btn.menu(), menu)
        self.assertEqual(btn.text(), "Dropdown Menu")


class ToolbarHandlerTestCase(unittest.TestCase):
    def setUp(self):
        self.main_window = QMainWindow()
        self.item = ToolbarItem(id="tlb_test", name="Toolbar Test", icon_size=32)
        self.handler = ToolbarHandler(self.item, enable_logs=True)

    def test_create_and_destroy_on_main_window(self):
        self.assertFalse(self.handler.is_created())
        self.handler.create(self.main_window)
        self.assertTrue(self.handler.is_created())

        act = QAction("Test Action", self.main_window)
        self.handler.add_action(act)
        self.handler.add_separator()
        btn = QPushButton("Test Button", self.main_window)
        self.handler.add_action_button(btn)

        menu = QMenu("Menu", self.main_window)
        drop_btn = QToolButton(self.main_window)
        drop_btn.setMenu(menu)
        self.handler.add_button_dropdown(drop_btn)
        self.handler.remove_button_dropdown(drop_btn)

        self.handler.destroy(self.main_window)
        self.assertFalse(self.handler.is_created())

    def test_create_and_destroy_with_layout(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        self.handler.create(container, layout=layout)
        self.assertTrue(self.handler.is_created())
        self.handler.destroy(container, layout=layout)
        self.assertFalse(self.handler.is_created())

    def test_operations_before_creation_log_errors(self):
        self.handler.add_action(QAction("A"))
        self.handler.add_separator()
        self.handler.add_action_button(QPushButton("B"))
        self.handler.add_button_dropdown(QToolButton())
        self.handler.remove_button_dropdown(QToolButton())
        self.handler.destroy(self.main_window)


class MenuMasterHandlerTestCase(unittest.TestCase):
    def setUp(self):
        self.main_window = QMainWindow()
        self.menu_bar = QMenuBar(self.main_window)
        self.menu = QMenu("File", self.main_window)
        self.theme = AppTheme()
        self.tlb_item = ToolbarItem(id="tlb_file", name="File Toolbar", icon_size=24)
        self.tlb_handler = ToolbarHandler(self.tlb_item, enable_logs=True)
        self.tlb_handler.create(self.main_window)

        self.master = MenuMasterHandler(
            menu=self.menu,
            menu_bar=self.menu_bar,
            parent=self.main_window,
            theme=self.theme,
            toolbar_handler=self.tlb_handler,
            enable_logs=True,
        )

    def test_install_and_uninstall_lifecycle(self):
        self.assertFalse(self.master.menu_installed)
        self.master.install_menu()
        self.assertTrue(self.master.menu_installed)

        self.master.install_toolbar()
        self.assertTrue(self.master.toolbar_installed)

        self.master.uninstall_menu()
        self.assertFalse(self.master.menu_installed)

        self.master.uninstall_toolbar()
        self.assertFalse(self.master.toolbar_installed)

    def test_install_action_and_updates(self):
        self.master.install_menu()
        self.master.install_toolbar()

        item = ActionItem(id="act_new", text="New File")
        setting = InstanceInstallSetting(menu_add=True, toolbar_add=True)
        data = InstanceData(settings=setting)

        # Install
        self.master.install_action(item=item, data=data)
        self.assertTrue(self.master.has_action_installed("act_new"))

        # Reinstall
        self.master.reinstall_all()

        # Update action
        trigger_mock = MagicMock()
        self.master.update_action("act_new", text="Updated New File", status=False, trigger=trigger_mock)
        act = self.master.inst_actions[0].action
        self.assertEqual(act.text(), "Updated New File")
        self.assertFalse(act.isEnabled())

        # Uninstall action
        self.master.uninstall_action(item)
        self.assertFalse(self.master.has_action_installed("act_new"))

    def test_install_action_group_inner_menu(self):
        self.master.install_menu()
        self.master.install_toolbar()

        a1 = ActionItem(id="opt1", text="Opt 1")
        a2 = ActionItem(id="opt2", text="Opt 2")
        grp = ActionGroupItem(id="grp_mode", actions=[a1, a2])
        inner_menu = QMenu("Mode Menu", self.main_window)
        setting = InstanceInstallSetting(menu_add=True, toolbar_add=True, toolbar_widget_type=ToolbarWidgetType.BUTTON_DROP_DOWN)
        data = InstanceData(settings=setting)

        self.master.install_group(item=grp, inner_menu=inner_menu, data=data)
        self.assertEqual(len(self.master.inst_group), 1)

        # Append action to group
        a3 = QAction("Opt 3", self.main_window)
        a3.setObjectName("opt3")
        self.master.append_action_to_group(a3, inner_menu)

        # Append dock action
        dock = QDockWidget("Test Dock", self.main_window)
        dock_item = ActionItem(id="dock_act", text="Show Dock")
        self.master.append_dock_show_action_menu(dock_item, dock, inner_menu=inner_menu)

        # Remove dock action
        self.master.remove_dock_show_action_menu(dock_item, dock, inner_menu=inner_menu)

        # Remove action from group
        self.master.remove_group_action(a1, inner_menu=inner_menu)

        # Uninstall group
        self.master.uninstall_group(grp)
        self.assertEqual(len(self.master.inst_group), 0)

    def test_install_action_group_direct(self):
        self.master.install_menu()
        self.master.install_toolbar()

        a1 = ActionItem(id="tool1", text="Tool 1")
        grp = ActionGroupItem(id="grp_tools", actions=[a1])
        setting = InstanceInstallSetting(menu_add=True, toolbar_add=True, toolbar_widget_type=ToolbarWidgetType.ACTION)
        data = InstanceData(settings=setting)

        self.master.install_group(item=grp, inner_menu=None, data=data)
        self.assertEqual(len(self.master.inst_group), 1)

        inst = self.master.inst_group[0]
        # Test add duplicate
        inst.add_action_to_group(inst.action_group.actions()[0])
        # Test remove action by id and by object
        inst.remove_action_from_group(action_id="tool1")
        inst.remove_action_from_group(action_id="nonexistent")

        self.master.uninstall_group(grp)

    def test_toolbar_switching_and_errors(self):
        # Error handling when already set
        new_handler = ToolbarHandler(ToolbarItem(id="tlb2", name="Toolbar 2", icon_size=24))
        self.master.set_toolbar_handler(new_handler)

        self.master.clear_toolbar_handler()
        self.assertIsNone(self.master.toolbar_handler)
        self.master.clear_toolbar_handler()  # second time error branch

        self.master.set_toolbar_handler(new_handler)
        self.assertEqual(self.master.toolbar_handler, new_handler)

    def test_instance_action_group_remove_exceptions(self):
        inst = InstanceActionGroup(
            parent=self.main_window,
            action_group_item=ActionGroupItem(id="test_grp", actions=[]),
        )
        with self.assertRaises(RuntimeError):
            inst.remove_action_from_group(action=None, action_id=None)


if __name__ == "__main__":
    unittest.main()
