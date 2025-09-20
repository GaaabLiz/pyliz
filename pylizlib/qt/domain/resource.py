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
        if self.color_light is not None and self.color_dark is not None:
            match theme.system_ui_mode:
                case OsTheme.LIGHT:
                    return self.color_light
                case OsTheme.DARK:
                    return self.color_dark
                case _:
                    return self.color
        return self.color

    def has_fixed_color(self):
        return (self.color is not None) or (self.color_light is None and self.color_dark is None)


@dataclass
class ResImage:
    res_id: str
