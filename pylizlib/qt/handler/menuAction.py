from typing import Any

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMainWindow, QDockWidget, QWidget, QMenu, QMenuBar, QHBoxLayout, \
    QVBoxLayout

from pylizlib.core.log.pylizLogger import logger
from pylizlib.qt.domain.menuActionTool import MenuActionHandlerData, ActionItem, InstanceData, ActionGroupItem, \
    ActionSignalType
from pylizlib.qt.domain.theme import AppTheme
from pylizlib.qt.handler.menuActionInst import InstanceAction, InstanceActionGroup
from pylizlib.qt.handler.menuActionToolbar import ToolbarHandler
from pylizlib.qt.util.menuActionTool import create_action_toggle_dock


# noinspection DuplicatedCode
class MenuMasterHandler:

    def __init__(
            self,
            menu: QMenu,
            menu_bar: QMenuBar,
            parent: Any,
            theme: AppTheme,
            toolbar_handler: ToolbarHandler | None = None,
            enable_logs: bool = False,
    ):
        self.parent = parent
        self.menu: QMenu = menu
        self.toolbar_handler = toolbar_handler
        self.menu_bar = menu_bar
        self.enable_logs = enable_logs
        self.theme = theme

        self.index_order = 0
        self.menu_installed = False
        self.toolbar_installed = False

        self.inst_actions: list[InstanceAction] = []
        self.inst_group: list[InstanceActionGroup] = []
        # self.separators: list[InstanceSeparator] = []

    def __get_handler_data(self) -> MenuActionHandlerData:
        return MenuActionHandlerData(
            theme=self.theme,
            enable_logs=self.enable_logs,
            toolbar_icon_size=self.__get_toolbar_icon_size()
        )

    def __is_menu_added(self):
        return self.menu in self.menu_bar.findChildren(QMenu)

    def __is_toolbar_available(self) -> bool:
        return self.toolbar_handler is not None

    def __get_toolbar_icon_size(self) -> int:
        if self.__is_toolbar_available():
            return self.toolbar_handler.item.icon_size
        return 32

    def __get_installed_actions(self, menu=None) -> list[QAction]:
        if menu is None:
            menu = self.menu
        all_actions = []
        for action in menu.actions():
            all_actions.append(action)
            submenu = action.menu()
            if submenu:
                all_actions.extend(self.__get_installed_actions(submenu))
        return all_actions

    def install_menu(self):
        if not self.__is_menu_added():
            self.menu_bar.addMenu(self.menu)
        self.menu_installed = True

    def install_toolbar(
            self,
            parent: QMainWindow | QDockWidget | QWidget | None = None,
            layout: QHBoxLayout | QVBoxLayout | None = None
    ):
        if self.__is_toolbar_available():
            parent_to_use = parent if parent else self.parent
            self.toolbar_handler.create(parent_to_use, layout)
            self.toolbar_installed = True
        else:
            logger.error("Cannot install toolbar %s. Toolbar is not available.", self.toolbar_handler.item.id)


    def uninstall_menu(self):
        if self.__is_menu_added():
            self.menu_bar.removeAction(self.menu.menuAction())
        self.menu_installed = False

    def uninstall_toolbar(self):
        if self.__is_toolbar_available():
            self.toolbar_handler.destroy(self.parent)
            self.toolbar_installed = False
        else:
            logger.error("Cannot uninstall toolbar %s. Toolbar is not available.", self.toolbar_handler.item.id)

    def set_toolbar_handler(self, toolbar_handler: ToolbarHandler):
        if self.__is_toolbar_available():
            logger.error("Cannot add toolbar handler %s. Toolbar handler is already set.", toolbar_handler.item.id)
            return
        self.toolbar_handler = toolbar_handler

    def clear_toolbar_handler(self):
        if not self.__is_toolbar_available():
            logger.error("Cannot clear toolbar handler %s. Toolbar handler is not set.", self.toolbar_handler.item.id)
            return
        self.toolbar_handler = None


    def has_action_installed(self, action_id: str) -> bool:
        for instance in self.inst_actions:
            if instance.action.objectName() == action_id:
                return True
        return False

    def reinstall_instance(self, inst: InstanceAction | InstanceActionGroup):
        logger.debug("Reinstalling instance %s", inst.type.value) if self.enable_logs else None
        inst.teardown()
        inst.menu_uninstall(self.menu)
        inst.toolbar_uninstall(self.toolbar_handler)
        inst.setup()
        inst.menu_install(self.menu)
        inst.toolbar_install(self.toolbar_handler)

    def reinstall_actions(self):
        if not self.menu_installed:
            logger.error("Cannot reinstall actions. Menu is not installed.")
            return
        for instance in self.inst_actions:
            self.reinstall_instance(instance)

    def reinstall_action_groups(self):
        if not self.menu_installed:
            logger.error("Cannot reinstall action groups. Menu is not installed.")
            return
        for instance in self.inst_group:
            self.reinstall_instance(instance)

    def reinstall_all(self):
        if not self.menu_installed:
            logger.error("Cannot reinstall all. Menu is not installed.")
            return
        self.reinstall_actions()
        self.reinstall_action_groups()

    def install_action(
            self,
            item: ActionItem,
            signal: Any | None = None,
            callback: Any | None = None,
            data: InstanceData = InstanceData(),
    ):
        try:
            if not self.menu_installed:
                raise RuntimeError("Menu is not installed.")
            if self.has_action_installed(item.id):
                raise RuntimeError("Action is already installed.")
            instance = InstanceAction(
                parent=self.parent,
                item=item,
                signal=signal,
                callback=callback,
                data=data,
                handler_data=self.__get_handler_data()
            )
            self.inst_actions.append(instance)
            instance.menu_install(self.menu)
            instance.toolbar_install(self.toolbar_handler)
        except Exception as e:
            logger.error("Error installing action %s: %s", item.id, str(e))
            return

    def install_group(
            self,
            item: ActionGroupItem,
            inner_menu: QMenu | None = None,
            signal: Any | None = None,
            signal_type: ActionSignalType = ActionSignalType.ACTION_OBJECT,
            data: InstanceData = InstanceData(),
    ):
        try:
            if not self.menu_installed:
                raise RuntimeError("Menu is not installed.")
            instance = InstanceActionGroup(
                parent=self.parent,
                action_group_item=item,
                inner_menu=inner_menu,
                signal=signal,
                signal_type=signal_type,
                data=data,
                handler_data=self.__get_handler_data()
            )
            self.inst_group.append(instance)
            instance.setup()
            instance.menu_install(self.menu)
            instance.toolbar_install(self.toolbar_handler)
        except Exception as e:
            logger.error("Error installing action group %s: %s", item.id, str(e))
            return

    def append_action_to_group(self, action: QAction, inner_menu: QMenu):
        if not self.menu_installed:
            logger.error("Cannot append action group %s. Menu is not installed.", action.objectName())
            return
        for instance in self.inst_group:
            if instance.inner_menu == inner_menu:
                instance.add_action_to_group(action)
                self.reinstall_instance(instance)
                break

    def append_dock_show_action_menu(self, item: ActionItem, dock: QDockWidget, inner_menu: QMenu | None = None):
        if not self.menu_installed:
            logger.error("Cannot append action %s. Menu is not installed.", item.id)
            return
        action = create_action_toggle_dock(item, dock)
        if inner_menu:
            self.append_action_to_group(action, inner_menu)

    def remove_dock_show_action_menu(self, item: ActionItem, dock: QDockWidget, inner_menu: QMenu | None = None):
        if not self.menu_installed:
            logger.error("Cannot remove action %s. Menu is not installed.", item.id)
            return
        if inner_menu:
            for instance in self.inst_group:
                if instance.inner_menu == inner_menu:
                    instance.remove_action_from_group(action_id=item.id)
                    self.reinstall_instance(instance)
                    break

    def remove_group_action(self, item: ActionItem, inner_menu: QMenu | None = None):
        if not self.menu_installed:
            logger.error("Cannot remove action %s. Menu is not installed.", item.id)
            return
        if inner_menu is None:
            self.uninstall_action(item)
        else:
            for instance in self.inst_group:
                if instance.inner_menu == inner_menu:
                    action = instance.get_action_from_group(item.id)
                    if action:
                        instance.remove_action_from_group(action)
                        self.reinstall_instance(instance)
                    break

    def uninstall_action(self, item: ActionItem):
        try:
            if not self.menu_installed:
                raise RuntimeError("Menu is not installed.")
            if not self.has_action_installed(item.id):
                raise RuntimeError("Action is not installed.")
            for instance in self.inst_actions:
                if instance.action.objectName() == item.id:
                    instance.menu_uninstall(self.menu)
                    instance.toolbar_uninstall(self.toolbar_handler)
                    self.inst_actions.remove(instance)
                    break
        except Exception as e:
            logger.error("Error uninstalling action %s: %s", item.id, str(e))
            return

    def uninstall_group(self, item: ActionGroupItem):
        try:
            if not self.menu_installed:
                raise RuntimeError("Menu is not installed.")
            for instance in self.inst_group:
                if instance.item.id == item.id:
                    logger.debug("Uninstalling action group with id %s", item.id)
                    instance.teardown()
                    instance.menu_uninstall(self.menu)
                    instance.toolbar_uninstall(self.toolbar_handler)
                    self.inst_group.remove(instance)
                    return
            raise RuntimeError("Cannot uninstall action group %s. Related instance not found", item.id)
        except Exception as e:
            logger.error("Error uninstalling action group %s: %s", item.id, str(e))
            return

    def update_action(
        self,
        action_id: str,
        text: str | None = None,
        status: bool | None = None,
        trigger: Any | None = None,
    ):
        for action in self.__get_installed_actions():
            if action.objectName() == action_id:
                if text is not None:
                    logger.debug("Updating text of action \"%s\" to \"%s\"", action_id, text) if self.enable_logs else None
                    action.setText(text)
                if status is not None:
                    logger.debug("Updating status of action \"%s\" to \"%s\"", action_id, status) if self.enable_logs else None
                    action.setEnabled(status)
                if trigger is not None:
                    logger.debug("Updating trigger of action \"%s\"", action_id) if self.enable_logs else None
                    action.triggered.connect(trigger)

