import itertools
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ClassVar

from PySide6.QtCore import Qt

from pylizlib.core.data.gen import gen_random_string
from pylizlib.qt.domain.resource import ResIcon
from pylizlib.qt.domain.theme import AppTheme


@dataclass
class ActionItem:
    id: str
    text: str
    text_for_group: str = "null"
    icon_res: ResIcon | None = None
    enabled: bool = True
    checkable: bool = False
    checked: bool = False
    visible: bool = True
    tags: list[str] = field(default_factory=list)
    shortcut: str | None = None
    menu_role: Any | None = None
    toolbar_group_adding: bool = False


@dataclass
class ToolbarItem:
    id: str
    name: str
    icon_size: int
    movable: bool = True
    orientation: Qt.Orientation = Qt.Orientation.Horizontal



@dataclass
class ActionGroupItem:
    id: str
    actions: list[ActionItem]
    exclusive: bool = False
    icon_res: ResIcon | None = None

    def get_action_item(self, action_id: str) -> ActionItem | None:
        for action in self.actions:
            if action.id == action_id:
                return action
        return None


class ActionSignalType(Enum):
    ACTION_OBJECT = 1
    ACTION_ID = 2


class ToolbarWidgetType(Enum):
    ACTION = 1
    BUTTON = 2
    BUTTON_DROP_DOWN = 3


@dataclass
class InstanceInstallSetting:
    menu_add: bool = True
    menu_use_group_text: bool = False
    toolbar_add: bool = False
    toolbar_widget_type: ToolbarWidgetType = ToolbarWidgetType.ACTION


class InstanceType(Enum):
    ACTION = 1
    ACTION_GROUP_INNER_MENU = 2
    ACTION_GROUP_PARENT_MENU = 3
    SEPARATOR = 4


INSTANCE_DEFAULT_FAMILY = "default"


@dataclass
class InstanceData:
    _order_counter: ClassVar[itertools.count] = itertools.count()

    id: str = gen_random_string(10)
    family: str = INSTANCE_DEFAULT_FAMILY
    order: int = field(init=False)
    settings: InstanceInstallSetting = field(default_factory=InstanceInstallSetting)

    def __post_init__(self):
        self.order = next(self._order_counter)


@dataclass
class MenuActionHandlerData:
    theme: AppTheme
    enable_logs: bool
    toolbar_icon_size: int
