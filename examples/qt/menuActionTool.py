import logging
import sys

from PySide6.QtCore import Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMainWindow, QMenu, QWidget, QVBoxLayout, QPushButton

from pylizlib.qt.domain.menuActionTool import ActionItem, InstanceData, InstanceInstallSetting, ToolbarWidgetType, \
    ActionGroupItem, ToolbarItem
from pylizlib.qt.domain.theme import AppTheme
from pylizlib.qt.handler.menuAction import MenuMasterHandler
from pylizlib.qt.handler.menuActionToolbar import ToolbarHandler

logging.basicConfig(
    level=logging.DEBUG,  # o DEBUG, WARNING, ERROR, CRITICAL
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),  # stampa su stdout
        # logging.FileHandler("app.log")  # se vuoi anche scrivere su file
    ]
)

logger = logging.getLogger(__name__)


class MenuActionToolWindow(QMainWindow):


    signal_action_1 = Signal()
    signal_action_2 = Signal()
    signal_action_3 = Signal(QAction)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Test Main Window")
        self.setGeometry(100, 100, 800, 600)

        self.action_1 = ActionItem("test_action_1", "Test Action 1")
        self.action_2 = ActionItem("test_action_2", "Test Action 2")
        self.action_3 = ActionItem("test_action_3", "Test Action 3")
        self.action_4 = ActionItem("test_action_4", "Test Action 4")
        self.action_5 = ActionItem("test_action_5", "Test Action 5")
        self.action_6 = ActionItem("test_action_6", "Test Action 6")

        self.toolbar = ToolbarHandler(ToolbarItem("test_toolbar", "Test Toolbar", 24))

        self.item_act_gp1 = ActionGroupItem(
            "test_action_group_1",
            actions=[self.action_3, self.action_4],
        )
        self.item_act_gp2 = ActionGroupItem(
            "test_action_group_2",
            actions=[self.action_5, self.action_6],
            exclusive=False,
        )

        self.data_1 = InstanceData(settings=InstanceInstallSetting(toolbar_add=True, toolbar_widget_type=ToolbarWidgetType.BUTTON_DROP_DOWN))
        self.data_2 = InstanceData(settings=InstanceInstallSetting(toolbar_add=True, toolbar_widget_type=ToolbarWidgetType.ACTION))
        self.data_3 = InstanceData(settings=InstanceInstallSetting(toolbar_add=True, toolbar_widget_type=ToolbarWidgetType.BUTTON))

        self.menu = QMenu("Menu 1")
        self.menu_inner_1 = QMenu("Inner 1")

        self.handler = MenuMasterHandler(
            menu=self.menu,
            menu_bar=self.menuBar(),
            parent=self,
            toolbar_handler=self.toolbar,
            enable_logs=True,
            theme=AppTheme()
        )
        self.handler.install_menu()
        self.handler.install_toolbar()

        # handler.install_action_group_inner(
        #     inner_menu=QMenu("Inner"),
        #     item=item_act_gp1,
        #     data=data_1,
        #     use_text_for_group=False
        # )

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Layout principale verticale (per centrare verticalmente)
        outer_layout = QVBoxLayout()
        outer_layout.addStretch()  # Spazio sopra
        button1 = QPushButton("ON")
        button2 = QPushButton("OFF")
        button1.clicked.connect(self.on)
        button2.clicked.connect(self.off)
        outer_layout.addWidget(button1)
        outer_layout.addWidget(button2)
        central_widget.setLayout(outer_layout)

        self.signal_action_3.connect(self.on_signal_action_3)

    def on_signal_action_1(self):
        pass

    def on_signal_action_2(self):
        pass

    def on_signal_action_3(self, action: QAction):
        print(f"Action triggered: {action.text()}")

    def on(self):
        self.handler.install_action(item=self.action_1, signal=self.signal_action_1,)
        self.handler.install_action(self.action_2, self.signal_action_2, )
        self.handler.install_group(
            item=self.item_act_gp1,
            inner_menu=self.menu_inner_1,
            signal=self.signal_action_3,
            data=self.data_1,
        )
        self.handler.install_group(
            item=self.item_act_gp2,
            signal=self.signal_action_3,
            data=self.data_1,
        )

    def off(self):
        self.handler.uninstall_action(self.action_1)
        self.handler.uninstall_action(self.action_2)
        self.handler.uninstall_group(self.item_act_gp1)
        self.handler.uninstall_group(self.item_act_gp2)



if __name__ == '__main__':

    app = QApplication(sys.argv)
    window = MenuActionToolWindow()
    window.show()
    sys.exit(app.exec())