import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("PySide6.QtGui")
pytest.importorskip("PySide6.QtWidgets")
pytest.importorskip("qfluentwidgets")

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QWidget
from qfluentwidgets import ConfigItem, Dialog, FluentIcon, PushButton, qconfig

from pylizlib.qtfw.domain.setting import QtFwQConfigGroup, QtFwQConfigItem
from pylizlib.qtfw.domain.sw import SoftwareData
from pylizlib.qtfw.model.qconfig import (
    ExecutableValidator,
    TextListValidator,
    count_elements_in_settings_keys,
)
from pylizlib.qtfw.util.ui import UiUtils
from pylizlib.qtfw.widgets.card import MasterListSettingCard, SoftwareListStatusGroupCard
from pylizlib.qtfw.widgets.data import FileItem
from pylizlib.qtfw.widgets.dialog.about import AboutMessageBox
from pylizlib.qtfw.widgets.input import LineEditMessageBox, MultiSelectionComboBox
from pylizlib.qtfw.widgets.progress import SimpleProgressDialog, SimpleProgressSettings
from pylizlib.qtfw.widgets.text import BoldLabel

os.environ["QT_QPA_PLATFORM"] = "offscreen"
app = QApplication.instance() or QApplication([])


class QtFwModelTestCase(unittest.TestCase):
    def test_executable_validator(self):
        val = ExecutableValidator()
        self.assertTrue(val.validate(sys.executable))
        self.assertFalse(val.validate("/non/existent/path/binary"))

        suffix = ".txt" if os.name == "nt" else ""
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
            non_executable_path = f.name
        try:
            if os.name != "nt":
                os.chmod(non_executable_path, 0o644)
            self.assertFalse(val.validate(non_executable_path))
            self.assertEqual(val.correct(non_executable_path), non_executable_path)
        finally:
            if os.path.exists(non_executable_path):
                os.remove(non_executable_path)

        executable_suffix = ".exe" if os.name == "nt" else ""
        with tempfile.NamedTemporaryFile(delete=False, suffix=executable_suffix) as f:
            executable_path = f.name
        try:
            if os.name != "nt":
                os.chmod(executable_path, 0o755)
            self.assertTrue(val.validate(executable_path))
            corrected = val.correct(executable_path)
            self.assertIn("/", corrected)
            self.assertNotIn("\\", corrected)
        finally:
            if os.path.exists(executable_path):
                os.remove(executable_path)

    def test_text_list_validator(self):
        val = TextListValidator()
        self.assertTrue(val.validate(["hello", "world"]))
        self.assertFalse(val.validate(["hello", ""]))
        self.assertFalse(val.validate(["hello", "   "]))
        self.assertFalse(val.validate(["hello", 123]))

        corrected = val.correct(["  hello ", "", "  world  ", "   "])
        self.assertEqual(corrected, ["hello", "world"])

    def test_count_elements_in_settings_keys(self):
        data = {
            "group1": {"files": ["a", "b"], "other": 123},
            "group2": {"files": ["c", "d", "e"]},
            "group3": {"not_files": ["f"]},
        }
        self.assertEqual(count_elements_in_settings_keys(data, "files"), 5)
        self.assertEqual(count_elements_in_settings_keys(data, "files", group="group1"), 2)
        self.assertEqual(count_elements_in_settings_keys(data, "missing_key"), 0)
        self.assertEqual(count_elements_in_settings_keys(data, "files", group="nonexistent"), 0)


class QtFwDomainTestCase(unittest.TestCase):
    def test_software_data(self):
        sw = SoftwareData(
            path=Path("/usr/bin/python"),
            is_service=False,
            icon=FluentIcon.PLAY,
            installed=True,
            running=False,
            version="3.12",
        )
        self.assertEqual(sw.path, Path("/usr/bin/python"))
        self.assertFalse(sw.is_service)
        self.assertEqual(sw.version, "3.12")

    def test_qtfw_qconfig_item_and_group(self):
        item = QtFwQConfigItem(
            enabled=True,
            group="General",
            name="TestItem",
            default="default_val",
        )
        self.assertTrue(item.enabled)
        self.assertEqual(item.value, "default_val")

        grp = QtFwQConfigGroup(name="GeneralGroup", description="My description", enabled=True)
        self.assertEqual(grp.name, "GeneralGroup")
        self.assertEqual(grp.description, "My description")
        self.assertTrue(grp.enabled)


class QtFwWidgetsTestCase(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        cfg_file = Path("config/config.json")
        if cfg_file.exists():
            cfg_file.unlink(missing_ok=True)
        cfg_dir = Path("config")
        if cfg_dir.exists() and not any(cfg_dir.iterdir()):
            cfg_dir.rmdir()

    def setUp(self):
        self.parent = QWidget()

    def test_bold_label(self):
        lbl = BoldLabel(self.parent)
        lbl.setText("Bold text")
        self.assertTrue(lbl.font().bold())
        self.assertEqual(lbl.text(), "Bold text")

    def test_file_item(self):
        item = FileItem("/path/to/my_file.txt", self.parent)
        self.assertEqual(item.file, "/path/to/my_file.txt")
        self.assertEqual(item.fileLabel.text(), "/path/to/my_file.txt")

        removed_events = []
        item.removed.connect(lambda widget: removed_events.append(widget))
        item.removeButton.click()
        self.assertEqual(removed_events, [item])

    def test_simple_progress_dialog(self):
        settings = SimpleProgressSettings(
            window_title="Testing Progress",
            window_label="In progress...",
            initial_status_text="Starting...",
        )
        dlg = SimpleProgressDialog(parent=self.parent, settings=settings)
        self.assertEqual(dlg.windowTitle(), "Testing Progress")
        self.assertEqual(dlg.title.text(), "In progress...")
        self.assertEqual(dlg.status.text(), "Starting...")

        dlg.set_maximum(200)
        self.assertEqual(dlg.progress_bar.maximum(), 200)

        dlg.update_progress(50, "Halfway done")
        self.assertEqual(dlg.progress_bar.value(), 50)
        self.assertEqual(dlg.status.text(), "Halfway done")

        dlg.update_status_only("Status change")
        self.assertEqual(dlg.status.text(), "Status change")

    def test_about_message_box(self):
        icon = QIcon()
        box = AboutMessageBox(icon=icon, app_name="MyTestApp", app_version="1.0.0", parent=self.parent)
        self.assertEqual(box.appNameLabel.text(), "MyTestApp")
        self.assertIn("1.0.0", box.versionLabel.text())
        self.assertTrue(box.validate())

    def test_line_edit_message_box(self):
        box = LineEditMessageBox(
            title="Enter Value",
            placeholder="Type here...",
            text_yes="OK",
            text_no="Cancel",
            parent=self.parent,
        )
        self.assertEqual(box.titleLabel.text(), "Enter Value")
        self.assertEqual(box.line_edit.placeholderText(), "Type here...")
        self.assertEqual(box.yesButton.text(), "OK")
        self.assertEqual(box.cancelButton.text(), "Cancel")

    def test_multi_selection_combo_box(self):
        combo = MultiSelectionComboBox(self.parent)
        combo.addItems(["Apple", "Banana", "Cherry"])
        self.assertEqual(combo.checkedItems(), [])
        self.assertEqual(combo.checkedIndexes(), [])

        # Set by indexes
        emitted = []
        combo.selectionChanged.connect(lambda items: emitted.append(items))
        combo.setCheckedIndexes([0, 2])
        self.assertEqual(combo.checkedIndexes(), [0, 2])
        self.assertEqual(combo.get_items(), ["Apple", "Cherry"])
        self.assertEqual(combo.text(), "Apple, Cherry")

        # Set by items
        combo.setCheckedItems(["Banana"])
        self.assertEqual(combo.get_items(), ["Banana"])

        # Test menu creation and toggling
        menu = combo._createComboMenu()
        act0 = menu.actions()[0]
        act0.setChecked(True)
        self.assertIn("Apple", combo.get_items())
        act0.setChecked(False)
        self.assertNotIn("Apple", combo.get_items())

        # Placeholder text
        combo.setPlaceholderText("Choose fruits...")
        combo.clearChecks()
        self.assertEqual(combo.get_items(), [])
        self.assertEqual(combo.text(), "Choose fruits...")

    def test_ui_utils_create_widget_act_bar_btn(self):
        class DummySignalEmitter(QObject):
            sig = Signal(str)

        emitter = DummySignalEmitter()
        received = []
        emitter.sig.connect(lambda txt: received.append(txt))

        data = ["Action 1", Path("/path/to/action2")]
        btn = UiUtils.create_widget_act_bar_btn(
            parent=self.parent,
            data=data,
            btn_name="Toolbar Action",
            icon=FluentIcon.SETTING,
            is_trasparent=True,
            clicked_signal=emitter.sig,
        )
        self.assertEqual(btn.text(), "Toolbar Action")
        actions = btn.menu().actions()
        self.assertEqual(len(actions), 2)
        actions[0].trigger()
        self.assertEqual(received, ["Action 1"])

        # Non transparent
        btn_non_trans = UiUtils.create_widget_act_bar_btn(
            parent=self.parent,
            data=["Action X"],
            btn_name="Non Transparent",
            icon=FluentIcon.SETTING,
            is_trasparent=False,
        )
        self.assertEqual(btn_non_trans.text(), "Non Transparent")

    def test_software_list_status_group_card(self):
        card = SoftwareListStatusGroupCard("Installed Tools", parent=self.parent)
        sw1 = SoftwareData(
            path=Path("/bin/git"),
            is_service=False,
            icon=FluentIcon.PLAY,
            installed=True,
            running=True,
            version="2.40",
        )
        sw2 = SoftwareData(
            path=Path("/bin/docker"),
            is_service=True,
            icon=FluentIcon.PAUSE,
            installed=False,
            running=False,
            version="Unknown",
        )
        card.add_software_data(sw1)
        card.add_software_data(sw2)
        card.update_all()

        w1 = card.groups[os.path.normcase(os.path.abspath(os.fspath(sw1.path)))]
        self.assertEqual(w1.label_installed.text(), "✅")
        self.assertEqual(w1.label_running.text(), "🟢")
        self.assertEqual(w1.label_version.text(), "2.40")

        w2 = card.groups[os.path.normcase(os.path.abspath(os.fspath(sw2.path)))]
        self.assertEqual(w2.label_installed.text(), "🚫")
        self.assertEqual(w2.label_running.text(), "🔴")

        card.clear_all_data()
        self.assertEqual(len(card.groups), 0)
        self.assertEqual(len(card.software_data), 0)

    @patch("pylizlib.qtfw.util.ui.Dialog")
    def test_ui_utils_show_message(self, mock_dialog_cls):
        mock_inst = MagicMock()
        mock_dialog_cls.return_value = mock_inst
        UiUtils.show_message("Info", "Some text message", parent=self.parent)
        mock_dialog_cls.assert_called_once_with("Info", "Some text message", self.parent)
        mock_inst.cancelButton.hide.assert_called_once()
        mock_inst.exec.assert_called_once()

    def test_master_list_setting_card_folder_flow(self):
        cfg_item = ConfigItem("TestGroup", "Folders", ["/existing/folder"])
        qconfig.set(cfg_item, ["/existing/folder"])

        btn = PushButton("Add Folder", self.parent)
        card = MasterListSettingCard(
            config_item=cfg_item,
            item_type=MasterListSettingCard.Type.FOLDER,
            card_title="Folders Card",
            card_icon=FluentIcon.FOLDER,
            card_content="Manage folders",
            main_btn=btn,
            dialog_title="Choose Folder",
            parent=self.parent,
        )
        self.assertEqual(card.items, ["/existing/folder"])

        changed = []
        card.item_changed.connect(lambda items: changed.append(items.copy()))

        with patch("pylizlib.qtfw.widgets.card.QFileDialog.getExistingDirectory", return_value="/new/folder"):
            btn.click()
            self.assertIn("/new/folder", card.items)
            self.assertEqual(len(changed), 1)

        # Remove item
        first_item_widget = card.viewLayout.itemAt(0).widget()
        card._MasterListSettingCard__remove_item(first_item_widget)
        self.assertNotIn("/existing/folder", card.items)

    def test_master_list_setting_card_file_and_text_flow(self):
        cfg_item = ConfigItem("TestGroup", "Files", [])
        qconfig.set(cfg_item, [])

        btn_file = PushButton("Add File", self.parent)
        card_file = MasterListSettingCard(
            config_item=cfg_item,
            item_type=MasterListSettingCard.Type.FILE,
            card_title="Files Card",
            card_icon=FluentIcon.DOCUMENT,
            card_content="Manage files",
            main_btn=btn_file,
            dialog_title="Choose File",
            parent=self.parent,
        )
        with patch("pylizlib.qtfw.widgets.card.QFileDialog.getOpenFileNames", return_value=(["/tmp/a.txt", "/tmp/b.txt"], "All Files")):
            btn_file.click()
            self.assertEqual(card_file.items, ["/tmp/a.txt", "/tmp/b.txt"])

        # Remove file
        first_widget = card_file.viewLayout.itemAt(0).widget()
        card_file._MasterListSettingCard__remove_item(first_widget)
        self.assertEqual(card_file.items, ["/tmp/b.txt"])

        # Text flow
        cfg_text = ConfigItem("TestGroup", "Texts", [])
        qconfig.set(cfg_text, [])
        btn_text = PushButton("Add Text", self.parent)
        card_text = MasterListSettingCard(
            config_item=cfg_text,
            item_type=MasterListSettingCard.Type.TEXT,
            card_title="Texts Card",
            card_icon=FluentIcon.FONT,
            card_content="Manage texts",
            main_btn=btn_text,
            dialog_title="Enter text",
            parent=self.parent,
        )
        with patch("pylizlib.qtfw.widgets.card.LineEditMessageBox") as mock_box_cls:
            mock_box = MagicMock()
            mock_box.exec.return_value = Dialog.DialogCode.Accepted
            mock_box.line_edit.text.return_value = "custom entry"
            mock_box_cls.return_value = mock_box
            btn_text.click()
            self.assertIn("custom entry", card_text.items)


if __name__ == "__main__":
    unittest.main()
