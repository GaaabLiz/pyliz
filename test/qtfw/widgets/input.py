import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from pylizlib.qtfw.widgets.input import MultiSelectionComboBox  # noqa: E402


class MultiSelectionComboBoxMutationTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_insert_and_remove_preserve_selected_item_identity(self):
        combo = MultiSelectionComboBox()
        combo.addItems(["first", "selected", "last"])
        combo.setCheckedItems(["selected"])

        combo.insertItem(0, "inserted")
        self.assertEqual(combo.get_items(), ["selected"])
        self.assertEqual(combo.checkedIndexes(), [2])

        combo.removeItem(0)
        self.assertEqual(combo.get_items(), ["selected"])
        self.assertEqual(combo.checkedIndexes(), [1])

        combo.removeItem(1)
        self.assertEqual(combo.get_items(), [])
        self.assertEqual(combo.checkedIndexes(), [])

    def test_duplicate_text_keeps_the_original_selected_item(self):
        combo = MultiSelectionComboBox()
        combo.addItems(["same", "other"])
        combo.setCheckedIndexes([0])

        combo.insertItem(0, "same")

        self.assertEqual(combo.checkedIndexes(), [1])
        self.assertEqual(combo.get_items(), ["same"])

    def test_clear_resets_and_emits_empty_selection(self):
        combo = MultiSelectionComboBox()
        combo.addItems(["first", "selected"])
        combo.setCheckedItems(["selected"])
        emitted = []
        combo.selectionChanged.connect(emitted.append)

        combo.clear()

        self.assertEqual(combo.get_items(), [])
        self.assertEqual(combo.checkedIndexes(), [])
        self.assertEqual(emitted, [[]])


if __name__ == "__main__":
    unittest.main()
