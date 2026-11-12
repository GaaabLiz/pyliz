import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, Signal  # noqa: E402
from PySide6.QtGui import QAction  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from pylizlib.qt.domain.menuActionTool import (  # noqa: E402
    ActionGroupItem,
    ActionItem,
    ActionSignalType,
)
from pylizlib.qt.domain.theme import AppTheme  # noqa: E402
from pylizlib.qt.util.menuActionTool import create_action_group  # noqa: E402


class TypedReceiver(QObject):
    action_id = Signal(str)


class CreateActionGroupTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_item(self):
        return ActionGroupItem(
            "tools",
            [ActionItem("tool.open", "Open")],
        )

    def test_action_id_mode_dispatches_object_name_to_callback(self):
        values = []
        parent = QWidget()
        group = create_action_group(
            self.make_item(),
            parent,
            AppTheme(),
            callback=values.append,
            signal_type=ActionSignalType.ACTION_ID,
        )

        group.actions()[0].trigger()

        self.assertEqual(values, ["tool.open"])
        self.assertIsInstance(values[0], str)

    def test_action_object_mode_dispatches_action_to_callback(self):
        values = []
        parent = QWidget()
        group = create_action_group(
            self.make_item(),
            parent,
            AppTheme(),
            callback=values.append,
            signal_type=ActionSignalType.ACTION_OBJECT,
        )

        group.actions()[0].trigger()

        self.assertEqual(len(values), 1)
        self.assertIsInstance(values[0], QAction)
        self.assertEqual(values[0].objectName(), "tool.open")

    def test_action_id_mode_supports_typed_string_signals(self):
        receiver = TypedReceiver()
        values = []
        receiver.action_id.connect(values.append)
        parent = QWidget()
        group = create_action_group(
            self.make_item(),
            parent,
            AppTheme(),
            signal=receiver.action_id,
            signal_type=ActionSignalType.ACTION_ID,
        )

        group.actions()[0].trigger()

        self.assertEqual(values, ["tool.open"])


if __name__ == "__main__":
    unittest.main()
