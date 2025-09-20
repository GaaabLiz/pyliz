from PySide6.QtGui import QAction, Qt
from PySide6.QtWidgets import QToolBar, QMainWindow, QDockWidget, QWidget, QPushButton, QHBoxLayout, \
    QVBoxLayout, QToolButton

from pylizlib.core.log.pylizLogger import logger
from pylizlib.qt.domain.menuActionTool import ToolbarItem
from pylizlib.qt.util.menuActionTool import create_toolbar


class ToolbarHandler:

    def __init__(
            self,
            item: ToolbarItem,
            enable_logs: bool = False,
    ):
        self.item: ToolbarItem = item
        self.toolbar: QToolBar | None = None
        self.created = False
        self.enable_logs = enable_logs

    def create(
            self,
            parent: QMainWindow | QDockWidget | QWidget,
            layout: QHBoxLayout | QVBoxLayout | None = None
    ):
        self.toolbar = create_toolbar(self.item, parent)
        if layout is None:
            parent.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.toolbar)
        else:
            layout.addWidget(self.toolbar)
        self.created = True
        logger.debug(f"Toolbar created for {self.item.id}") if self.enable_logs else None

    def destroy(self, parent: QMainWindow | QDockWidget | QWidget, layout: QHBoxLayout | QVBoxLayout | None = None):
        if self.toolbar:
            if layout is None:
                parent.removeToolBar(self.toolbar)
            else:
                layout.removeWidget(self.toolbar)
            self.toolbar.deleteLater()
            self.toolbar = None
            self.created = False
            logger.debug(f"Toolbar destroyed for {self.item.id}") if self.enable_logs else None
        else:
            logger.error("Cannot destroy toolbar %s. Toolbar is not created.", self.item.id)

    def is_created(self) -> bool:
        return self.toolbar is not None and self.created

    def add_action(self, action: QAction):
        if self.is_created():
            self.toolbar.addAction(action)
            logger.debug("Added action %s to toolbar %s", action.objectName(), self.item.id) if self.enable_logs else None
        else:
            logger.error("Cannot add action to toolbar %s. Toolbar is not created.", self.item.id)

    def add_separator(self):
        if self.is_created():
            self.toolbar.addSeparator()
            logger.debug("Added separator to toolbar %s", self.item.id) if self.enable_logs else None
        else:
            logger.error("Cannot add separator to toolbar %s. Toolbar is not created.", self.item.id)

    def add_action_button(self, button: QPushButton):
        if self.is_created():
            self.toolbar.addWidget(button)
            logger.debug("Added button %s to toolbar %s", button.objectName(), self.item.id) if self.enable_logs else None
        else:
            logger.error("Cannot add button to toolbar %s. Toolbar is not created.", self.item.id)

    def add_button_dropdown(self, button: QToolButton):
        if self.is_created():
            self.toolbar.addWidget(button)
            logger.debug("Added button %s to toolbar %s", button.objectName(), self.item.id) if self.enable_logs else None
        else:
            logger.error("Cannot add button to toolbar %s. Toolbar is not created.", self.item.id)

    def remove_button_dropdown(self, button: QToolButton):
        if self.is_created():
            self.toolbar.removeAction(button.menu().menuAction())
            for action in self.toolbar.actions():
                if self.toolbar.widgetForAction(action) is button:
                    self.toolbar.removeAction(action)
                    button.deleteLater()
                    break
            logger.debug("Removed button %s from toolbar %s", button.objectName(), self.item.id) if self.enable_logs else None
        else:
            logger.error("Cannot remove button from toolbar %s. Toolbar is not created.", self.item.id)

