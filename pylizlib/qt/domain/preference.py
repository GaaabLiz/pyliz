from dataclasses import dataclass
from enum import Enum
from typing import Callable

from PySide6.QtWidgets import QSpinBox, QLabel, QComboBox, QCheckBox

from pylizlib.qt.domain.config import QtConfigItem
from pylizlib.qt.widget.data import PathLineSelector


@dataclass
class PreferenceItemPath:
    label: QLabel
    widget: PathLineSelector
    config_id: str
    getter: Callable
    setter: Callable


@dataclass
class PreferenceItemCheck:
    label: QLabel
    widget: QCheckBox
    config_id: str
    getter: Callable
    setter: Callable


@dataclass
class PreferenceItemCombo:
    label: QLabel
    widget: QComboBox
    config_id: str
    getter: Callable
    setter: Callable


@dataclass
class PreferenceItemSpinBox:
    label: QLabel
    widget: QSpinBox
    config_id: str
    getter: Callable
    setter: Callable


class PreferenceTypes(Enum):
    PATH = "PATH"
    CHECK = "CHECK"
    COMBO = "COMBO"
    SPINBOX = "SPINBOX"


@dataclass
class PreferenceConfigData:
    config: QtConfigItem
    type: PreferenceTypes


@dataclass
class PreferenceTabGroup:
    tab: str
    section: str
    config_list: list[PreferenceConfigData]

