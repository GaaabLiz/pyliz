from dataclasses import dataclass

from PySide6.QtGui import QColor

from pylizlib.core.domain.os import OsTheme
from pylizlib.qt.domain.theme import AppTheme


@dataclass
class ResIcon:
    res_id: str
    color: QColor | None = None
    color_light: QColor | None = None
    color_dark: QColor | None = None

    def get_color(self, theme: AppTheme):
        if self.color is not None:
            return self.color
        match theme.system_ui_mode:
            case OsTheme.LIGHT:
                return self.color_light
            case OsTheme.DARK:
                return self.color_dark
            case _:
                return None

    def has_fixed_color(self):
        return self.color is not None


@dataclass
class ResImage:
    res_id: str
