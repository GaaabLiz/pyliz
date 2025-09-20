from typing import Any

from PySide6.QtCore import QSettings

from pylizlib.qt.domain.config import QtConfigItem


class ConfigQtHandler:

    @staticmethod
    def qt_write(item: QtConfigItem, value: Any, setting: QSettings) -> None:
        if item.type == list:
            assert item.max_list_size is not None, "max_list_size must be set for list type"
            ConfigQtHandler.__qt_write_list(item, value, setting)
        if item.type == str:
            ConfigQtHandler.__qt_write_str(item, value, setting)

    @staticmethod
    def qt_read(
            item: QtConfigItem,
            setting: QSettings,
            return_default_if_none: bool = False,

    ) -> Any:
        history: Any = setting.value(item.id, item.default, type=item.type)
        if history is None and return_default_if_none:
            return item.default
        return history

    @staticmethod
    def qt_clear_all(setting: QSettings) -> None:
        setting.clear()
        setting.sync()

    @staticmethod
    def __qt_write_list(item: QtConfigItem, value: Any, setting: QSettings):
        history: Any = setting.value(item.id, item.default, type=item.type)
        if value in history:
            history.remove(value)
        history.insert(0, value)
        history = history[:item.max_list_size]
        setting.setValue(item.id, history)

    @staticmethod
    def __qt_write_str(item: QtConfigItem, value: Any, setting: QSettings):
        setting.setValue(item.id, value)

    @staticmethod
    def get_qt_file_path(setting: QSettings) -> str:
        return setting.fileName()