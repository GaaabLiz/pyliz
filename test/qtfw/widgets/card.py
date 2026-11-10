import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pylizlib.qtfw.widgets.card import MasterListSettingCard


class MasterListSettingCardTestCase(unittest.TestCase):
    def test_folder_removal_updates_list_and_persists_change(self):
        folder = "/media/archive"
        config_item = object()
        card = SimpleNamespace(
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


if __name__ == "__main__":
    unittest.main()
