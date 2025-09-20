from abc import abstractmethod, ABC
from typing import Any, Optional

from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMainWindow, QPushButton, QMenu, QToolButton

from pylizlib.core.log.pylizLogger import logger
from pylizlib.qt.domain.menuActionTool import InstanceType, InstanceData, ToolbarWidgetType, ActionItem, \
    MenuActionHandlerData, ActionGroupItem, ActionSignalType
from pylizlib.qt.domain.theme import AppTheme
from pylizlib.qt.handler.menuActionToolbar import ToolbarHandler
from pylizlib.qt.handler.resource import ResHandler
from pylizlib.qt.util.menuActionTool import create_action, create_action_group, create_menu_action_drop_button


class Instance(ABC):

    def __init__(self, inst_type: InstanceType, data: InstanceData):
        self.order = data.order
        self.family = data.family
        self.settings = data.settings
        self.type = inst_type
        self.menu_installed: bool = False
        self.toolbar_installed: bool = False



    def setup(self):
        pass

    def teardown(self):
        pass

    @abstractmethod
    def menu_install(self, menu: QMenu):
        pass

    @abstractmethod
    def menu_uninstall(self, menu: QMenu):
        pass

    @abstractmethod
    def toolbar_install(self, toolbar_handler: Optional[ToolbarHandler]):
        pass

    @abstractmethod
    def toolbar_uninstall(self, toolbar_handler: Optional[ToolbarHandler]):
        pass

    def handle_tlb_action_adding(
            self,
            toolbar_handler: ToolbarHandler,
            action: QAction | None = None,
            button: QPushButton | None = None,
            drop_button: QToolButton | None = None,
    ):
        if self.settings.toolbar_widget_type == ToolbarWidgetType.ACTION:
            if action is None:
                logger.error("Cannot add action to toolbar %s. Action is None.", toolbar_handler.item.id)
                return
            toolbar_handler.add_action(action)
        elif self.settings.toolbar_widget_type == ToolbarWidgetType.BUTTON:
            if button is None:
                logger.error("Cannot add button to toolbar %s. Button is None.", toolbar_handler.item.id)
                return
            toolbar_handler.add_action_button(button)
        elif self.settings.toolbar_widget_type == ToolbarWidgetType.BUTTON_DROP_DOWN:
            if drop_button is None:
                logger.error("Cannot add button drop down to toolbar %s. DropDown Button is None.", toolbar_handler.item.id)
                return
            toolbar_handler.add_button_dropdown(drop_button)

    def handle_tlb_action_removal(
            self,
            toolbar_handler: ToolbarHandler,
            action: QAction | None = None,
            button: QPushButton | None = None,
            drop_button: QToolButton | None = None,
    ):
        if self.settings.toolbar_widget_type == ToolbarWidgetType.ACTION:
            if action is None:
                logger.error("Cannot remove action from toolbar %s. Action is None.", toolbar_handler.item.id)
                return
            toolbar_handler.toolbar.removeAction(action)
        elif self.settings.toolbar_widget_type == ToolbarWidgetType.BUTTON:
            # if button is None:
            #     logger.error("Cannot remove button from toolbar %s. Button is None.", toolbar_handler.item.id)
            #     return
            # for btn_action in toolbar_handler.toolbar.actions():
            #     if btn_action.text() == button.text():
            #         toolbar_handler.toolbar.removeAction(btn_action)
            print("Not implemented yet")
            pass
        elif self.settings.toolbar_widget_type == ToolbarWidgetType.BUTTON_DROP_DOWN:
            if drop_button is None:
                logger.error("Cannot remove button drop down from toolbar %s. DropDown Button is None.", toolbar_handler.item.id)
                return
            toolbar_handler.remove_button_dropdown(drop_button)

            # toolbar_handler.toolbar.removeAction(drop_button)




class InstanceAction(Instance):

    def __init__(
            self,
            parent: QMainWindow,
            item: ActionItem,
            signal: Any | None = None,
            callback: Any | None = None,
            data: InstanceData = InstanceData(),
            handler_data: MenuActionHandlerData = MenuActionHandlerData(AppTheme(), False, 32),
    ):
        super().__init__(InstanceType.ACTION, data)
        self.item = item
        self.action = create_action(
            item=item,
            parent=parent,
            signal=signal,
            theme=handler_data.theme,
            callback=callback,
            toolbar_icon_size=handler_data.toolbar_icon_size,
        )
        self.enable_logs = handler_data.enable_logs

    def menu_install(self, menu: QMenu):
        if self.settings.menu_add:
            logger.debug("Installing action %s to menu %s", self.action.objectName(), menu.title()) if self.enable_logs else None
            menu.addAction(self.action)
            self.menu_installed = True

    def menu_uninstall(self, menu: QMenu):
        if self.settings.menu_add:
            logger.debug("Uninstalling action %s from menu %s", self.action.objectName(), menu.title()) if self.enable_logs else None
            menu.removeAction(self.action)
            self.menu_installed = False

    def toolbar_install(self, toolbar_handler: Optional[ToolbarHandler]):
        if self.settings.toolbar_add and toolbar_handler:
            logger.debug("Installing action %s to toolbar %s", self.action.objectName(), toolbar_handler.item.id) if self.enable_logs else None
            self.handle_tlb_action_adding(toolbar_handler, action=self.action)

    def toolbar_uninstall(self, toolbar_handler: Optional[ToolbarHandler]):
        if self.settings.toolbar_add and toolbar_handler:
            self.handle_tlb_action_removal(toolbar_handler, action=self.action)


class InstanceActionGroup(Instance):
    def __init__(
            self,
            parent: QMainWindow,
            action_group_item: ActionGroupItem,
            inner_menu: QMenu | None = None,
            signal: Any | None = None,
            signal_type: ActionSignalType = ActionSignalType.ACTION_OBJECT,
            callback: Any | None = None,
            data: InstanceData = InstanceData(),
            handler_data: MenuActionHandlerData = MenuActionHandlerData(AppTheme(), False, 32),
    ):
        super().__init__(InstanceType.ACTION_GROUP_INNER_MENU, data)
        self.action_group = create_action_group(
            item=action_group_item,
            parent=parent,
            signal=signal,
            use_text_for_group=data.settings.menu_use_group_text,
            signal_type=signal_type,
            theme=handler_data.theme,
            callback=callback,
        )
        self.item: ActionGroupItem = action_group_item
        self.inner_menu = inner_menu
        self.is_inner = self.inner_menu is not None
        self.enable_logs = handler_data.enable_logs
        self.theme = handler_data.theme
        self.widgets_dropdown: list[QToolButton] = []

    def get_action_from_group(self, action_id: str) -> QAction | None:
        for action in self.action_group.actions():
            if action.objectName() == action_id:
                return action
        return None
    #
    def add_action_to_group(self, action: QAction):
        if action not in self.action_group.actions():
            self.action_group.addAction(action)
        else:
            logger.warning("Action %s already in group %s", action.text(), self.action_group.objectName())

    def remove_action_from_group(self, action: QAction | None = None,  action_id: str | None = None):
        if action is None and action_id is None:
            raise RuntimeError("Cannot remove action from group %s. Action and action_id are None.", self.action_group.objectName())
        if action is None:
            act = self.get_action_from_group(action_id)
            if act:
                self.action_group.removeAction(act)
            else:
                logger.warning("Action %s not in group %s", action_id, self.action_group.objectName())
        elif action is not None:
            if action in self.action_group.actions():
                self.action_group.removeAction(action)
            else:
                logger.warning("Action %s not in group %s", action.text(), self.action_group.objectName())

    def __get_group_icon(self) -> QIcon | None:
        if self.item.icon_res:
            return ResHandler.get_icon(self.item.icon_res, self.theme)
        return None

    def setup(self):
        if self.is_inner:
            self.inner_menu.addActions(self.action_group.actions())
            logger.debug("Added %s actions to inner menu %s", len(self.action_group.actions()), self.inner_menu.title()) if self.enable_logs else None

    def teardown(self):
        if self.is_inner:
            for action in self.action_group.actions():
                self.inner_menu.removeAction(action)
            self.inner_menu.clear()

    def menu_install(self, menu: QMenu):
        if self.settings.menu_add:
            if self.is_inner:
                logger.debug("Installing action group %s to menu %s", self.action_group.objectName(), menu.title()) if self.enable_logs else None
                menu.addMenu(self.inner_menu)
            else:
                menu.addActions(self.action_group.actions())

    def menu_uninstall(self, menu: QMenu):
        if self.settings.menu_add:
            if self.is_inner:
                menu.removeAction(self.inner_menu.menuAction())
            else:
                for action in self.action_group.actions():
                    menu.removeAction(action)

    def toolbar_install(self, toolbar_handler: Optional[ToolbarHandler]):
        if self.settings.toolbar_add and toolbar_handler:
            match self.settings.toolbar_widget_type:
                case ToolbarWidgetType.ACTION:
                    for action in self.action_group.actions():
                        self.handle_tlb_action_adding(toolbar_handler, action=action)
                case ToolbarWidgetType.BUTTON:
                    # action_item = self.item.get_action_item(action.objectName())
                    # if action_item is None:
                    #     raise RuntimeError(f"Action item {action.objectName()} not found during toolbar installation of type BUTTON")
                    # btn = create_action_btn_push(
                    #     item=self.item.get_action_item(action.objectName()),
                    #     action=action,
                    #     parent=toolbar_handler.toolbar,
                    # )
                    # self.handle_tlb_action_adding(toolbar_handler, button=btn)
                    pass
                case ToolbarWidgetType.BUTTON_DROP_DOWN:
                    if self.is_inner:
                        drop_button = create_menu_action_drop_button(
                            menu=self.inner_menu,
                            icon=self.__get_group_icon()
                        )
                    else:
                        drop_menu = QMenu(title=self.action_group.objectName())
                        for action in self.action_group.actions():
                            logger.debug("Adding action %s to drop menu %s", action.objectName(), drop_menu.title()) if self.enable_logs else None
                            drop_menu.addAction(action)
                        drop_button = create_menu_action_drop_button(
                            menu=drop_menu,
                            icon=self.__get_group_icon()
                        )
                    self.handle_tlb_action_adding(toolbar_handler, drop_button=drop_button)
                    self.widgets_dropdown.append(drop_button)

    def toolbar_uninstall(self, toolbar_handler: Optional[ToolbarHandler]):
        if self.settings.toolbar_add and toolbar_handler:
            match self.settings.toolbar_widget_type:
                case ToolbarWidgetType.ACTION:
                    for action in self.action_group.actions():
                        self.handle_tlb_action_removal(toolbar_handler, action=action)
                case ToolbarWidgetType.BUTTON_DROP_DOWN:
                    for btn in self.widgets_dropdown:
                        self.handle_tlb_action_removal(toolbar_handler, drop_button=btn)



