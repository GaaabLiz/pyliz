import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from pylizlib.qtfw.domain.sw import SoftwareData  # noqa: E402
from pylizlib.qtfw.widgets.card import MasterListSettingCard, SoftwareListStatusGroupCard  # noqa: E402


class MasterListSettingCardTestCase(unittest.TestCase):
    def test_folder_removal_updates_list_and_persists_change(self):
        folder = "/media/archive"
        config_item = object()
        card = SimpleNamespace(
            Type=MasterListSettingCard.Type,
            item_type=MasterListSettingCard.Type.FOLDER,
            items=[folder],
            configItem=config_item,
            viewLayout=MagicMock(),
            item_changed=MagicMock(),
            _adjustViewSize=MagicMock(),
        )
        item = MagicMock()
        item.file = folder

        with patch("pylizlib.qtfw.widgets.card.qconfig.set") as set_config:
            MasterListSettingCard._MasterListSettingCard__remove_item(card, item)

        self.assertEqual(card.items, [])
        card.viewLayout.removeWidget.assert_called_once_with(item)
        item.deleteLater.assert_called_once()
        set_config.assert_called_once_with(config_item, [])
        card.item_changed.emit.assert_called_once_with([])


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
