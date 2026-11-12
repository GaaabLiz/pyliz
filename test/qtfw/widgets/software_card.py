import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from pylizlib.qtfw.domain.sw import SoftwareData  # noqa: E402
from pylizlib.qtfw.widgets.card import SoftwareListStatusGroupCard  # noqa: E402


class SoftwareListStatusGroupCardTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def make_data(path):
        return SoftwareData(Path(path), False, None, True, False, "1.0")

    def test_same_filename_in_different_directories_keeps_both_widgets(self):
        card = SoftwareListStatusGroupCard("Software")
        first_widget = MagicMock()
        second_widget = MagicMock()
        first_data = self.make_data("/first/tool.exe")
        second_data = self.make_data("/second/tool.exe")

        with (
            patch.object(card, "addGroup"),
            patch.object(
                SoftwareListStatusGroupCard,
                "SoftwareDataWidget",
                side_effect=[first_widget, second_widget],
            ),
        ):
            card.add_software_data(first_data)
            card.add_software_data(second_data)
            card.update_all()

        self.assertEqual(len(card.groups), 2)
        first_widget.update_data.assert_called_once()
        second_widget.update_data.assert_called_once()

        card.clear_all_data()

        first_widget.setParent.assert_called_once_with(None)
        first_widget.deleteLater.assert_called_once()
        second_widget.setParent.assert_called_once_with(None)
        second_widget.deleteLater.assert_called_once()
        self.assertEqual(card.groups, {})
        self.assertEqual(card.software_data, [])


if __name__ == "__main__":
    unittest.main()
