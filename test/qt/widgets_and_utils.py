import os
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from pylizlib.qt.domain.config import QtConfigItem
from pylizlib.qt.domain.preference import (
    PreferenceConfigData,
    PreferenceItemCheck,
    PreferenceItemCombo,
    PreferenceItemPath,
    PreferenceItemSpinBox,
    PreferenceTabGroup,
    PreferenceTypes,
)
from pylizlib.qt.domain.view import UiWidgetMode
from pylizlib.qt.util.preference import create_prf_group_box_form_layout
from pylizlib.qt.util.ui import UiUtils
from pylizlib.qt.widget.data import PathLineSelector
from pylizlib.qt.widget.status import QtLizStatusBar

os.environ["QT_QPA_PLATFORM"] = "offscreen"
app = QApplication.instance() or QApplication([])


class QtWidgetsAndUtilsTestCase(unittest.TestCase):
    def test_ui_utils_clear_layout(self):
        parent_widget = QWidget()
        v_layout = QVBoxLayout(parent_widget)
        lbl1 = QLabel("Child 1", parent_widget)
        lbl2 = QLabel("Child 2", parent_widget)
        sub_layout = QVBoxLayout()
        lbl3 = QLabel("Sub child", parent_widget)
        sub_layout.addWidget(lbl3)

        v_layout.addWidget(lbl1)
        v_layout.addWidget(lbl2)
        v_layout.addLayout(sub_layout)

        self.assertEqual(v_layout.count(), 3)
        UiUtils.clear_layout(v_layout)
        self.assertEqual(v_layout.count(), 0)

    def test_create_prf_group_box_form_layout(self):
        parent = QWidget()
        group_box, form_layout = create_prf_group_box_form_layout("Test Settings", parent)
        self.assertEqual(group_box.title(), "Test Settings")
        self.assertIsNotNone(form_layout)

    def test_path_line_selector_folder_mode(self):
        selector = PathLineSelector(select_file=False)
        self.assertFalse(selector.select_file)

        # Set and get text
        selector.setText("/path/to/folder")
        self.assertEqual(selector.text(), "/path/to/folder")

        # Open dialog mocked
        with patch("PySide6.QtWidgets.QFileDialog.getExistingDirectory", return_value="/selected/dir"):
            selector.open_dialog()
            self.assertEqual(selector.text(), "/selected/dir")

        with patch("PySide6.QtWidgets.QFileDialog.getExistingDirectory", return_value=""):
            selector.open_dialog()
            self.assertEqual(selector.text(), "/selected/dir")  # unchanged when cancelled

    def test_path_line_selector_file_mode(self):
        selector = PathLineSelector(select_file=True)
        self.assertTrue(selector.select_file)

        with patch("PySide6.QtWidgets.QFileDialog.getOpenFileName", return_value=("/selected/file.txt", "All Files (*.*)")):
            selector.open_dialog()
            self.assertEqual(selector.text(), "/selected/file.txt")

        # Signals
        text_changes = []
        selector.get_text_changed().connect(lambda t: text_changes.append(t))
        selector.setText("/new/path")
        self.assertIn("/new/path", text_changes)

    def test_qtliz_status_bar(self):
        parent = QWidget()
        status_bar = QtLizStatusBar(parent)
        self.assertEqual(status_bar.currentMessage(), "Ready")

        # Progress bar updates
        status_bar.update_progress_bar(40)
        self.assertEqual(status_bar.progress_bar.value(), 40)
        self.assertFalse(status_bar.progress_bar.isHidden())

        # Progress bar hides at 100%
        status_bar.update_progress_bar(100)
        self.assertEqual(status_bar.progress_bar.value(), 100)
        self.assertTrue(status_bar.progress_bar.isHidden())

        # Custom message
        status_bar.set_status_message("Processing...")
        self.assertEqual(status_bar.currentMessage(), "Processing...")

    def test_preference_domain_models(self):
        item_path = PreferenceItemPath(
            label=QLabel("P"),
            widget=PathLineSelector(),
            config_id="c_path",
            getter=lambda: "/p",
            setter=lambda v: None,
        )
        item_check = PreferenceItemCheck(
            label=QLabel("C"),
            widget=QCheckBox(),
            config_id="c_check",
            getter=lambda: True,
            setter=lambda v: None,
        )
        item_combo = PreferenceItemCombo(
            label=QLabel("Cb"),
            widget=QComboBox(),
            config_id="c_combo",
            getter=lambda: "opt1",
            setter=lambda v: None,
        )
        item_spin = PreferenceItemSpinBox(
            label=QLabel("S"),
            widget=QSpinBox(),
            config_id="c_spin",
            getter=lambda: 10,
            setter=lambda v: None,
        )

        conf_data = PreferenceConfigData(
            config=QtConfigItem(id="cfg", type=str, default=""),
            type=PreferenceTypes.PATH,
        )
        tab_group = PreferenceTabGroup(
            tab="General",
            section="Paths",
            config_list=[conf_data],
        )

        self.assertEqual(item_path.config_id, "c_path")
        self.assertEqual(item_check.config_id, "c_check")
        self.assertEqual(item_combo.config_id, "c_combo")
        self.assertEqual(item_spin.config_id, "c_spin")
        self.assertEqual(tab_group.tab, "General")
        self.assertEqual(tab_group.section, "Paths")
        self.assertEqual(len(tab_group.config_list), 1)

    def test_ui_widget_mode_enum(self):
        self.assertEqual(UiWidgetMode.DISPLAYING.value, "displaying")
        self.assertEqual(UiWidgetMode.UPDATING.value, "updating")


if __name__ == "__main__":
    unittest.main()
