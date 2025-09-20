
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer

from pylizlib.qt.domain.resource import ResIcon, ResImage
from pylizlib.qt.domain.theme import AppTheme


class ResHandler:

    @staticmethod
    def colored_svg_icon(res: str, size: QSize, color: QColor) -> QIcon:
        # Carica SVG
        renderer = QSvgRenderer(res)

        # Crea una pixmap trasparente
        pixmap = QPixmap(size)
        pixmap.fill(Qt.GlobalColor.transparent)

        # Disegna l'SVG nella pixmap con colore sovrascritto
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Applica un colore con CompositionMode_SourceIn
        renderer.render(painter)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(pixmap.rect(), color)

        painter.end()

        return QIcon(pixmap)

    @staticmethod
    def __get_icon_color(icon: ResIcon, theme: AppTheme):
        if icon.has_fixed_color():
            return icon.get_color(theme)
        return theme.ui.get_primary_color()

    @staticmethod
    def get_icon(
            icon: ResIcon,
            theme: AppTheme,
            theme_style: bool = False,
            icon_size: int = 32,
    ) -> QIcon:
        if not theme_style:
            return QIcon(icon.res_id)
        color = ResHandler.__get_icon_color(icon, theme)
        return ResHandler.colored_svg_icon(icon.res_id, QSize(icon_size, icon_size), color)

    @staticmethod
    def get_icon_image(image: ResImage) -> QIcon:
        return QIcon(image.res_id)

    @staticmethod
    def get_image(image: ResImage) -> QPixmap:
        return QPixmap(image.res_id)