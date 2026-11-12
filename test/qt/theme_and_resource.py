import os
import unittest

from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import QApplication

from pylizlib.core.domain.os import OsTheme
from pylizlib.qt.domain.resource import ResIcon, ResImage
from pylizlib.qt.domain.theme import AppTheme, UiTheme
from pylizlib.qt.handler.resource import ResHandler

os.environ["QT_QPA_PLATFORM"] = "offscreen"
app = QApplication.instance() or QApplication([])


class ThemeAndResourceTestCase(unittest.TestCase):
    def test_ui_theme_get_primary_color(self):
        theme = UiTheme(
            mode=None,
            primary_color=QColor("blue"),
            primary_color_light=QColor("lightblue"),
            primary_color_dark=QColor("darkblue"),
        )
        # mode is None -> primary_color
        self.assertEqual(theme.get_primary_color(), QColor("blue"))

        # mode is LIGHT -> primary_color_light
        theme.mode = OsTheme.LIGHT
        self.assertEqual(theme.get_primary_color(), QColor("lightblue"))

        # mode is DARK -> primary_color_dark
        theme.mode = OsTheme.DARK
        self.assertEqual(theme.get_primary_color(), QColor("darkblue"))

    def test_res_icon_colors_and_fixed(self):
        # Fixed color icon
        icon_fixed = ResIcon(res_id=":icons/app.png", color=QColor("red"))
        self.assertTrue(icon_fixed.has_fixed_color())
        app_theme = AppTheme(system_ui_mode=OsTheme.LIGHT)
        self.assertEqual(icon_fixed.get_color(app_theme), QColor("red"))

        # Adaptive icon for Light / Dark mode
        icon_adaptive = ResIcon(
            res_id=":icons/gear.svg",
            color_light=QColor("white"),
            color_dark=QColor("black"),
        )
        self.assertFalse(icon_adaptive.has_fixed_color())

        app_theme.system_ui_mode = OsTheme.LIGHT
        self.assertEqual(icon_adaptive.get_color(app_theme), QColor("white"))

        app_theme.system_ui_mode = OsTheme.DARK
        self.assertEqual(icon_adaptive.get_color(app_theme), QColor("black"))

        app_theme.system_ui_mode = OsTheme.UNKNOWN
        self.assertIsNone(icon_adaptive.get_color(app_theme))

    def test_res_handler_icons_and_images(self):
        icon = ResIcon(res_id=":icons/test.png")
        image = ResImage(res_id=":images/test.png")
        app_theme = AppTheme()

        qicon = ResHandler.get_icon(icon, app_theme, theme_style=False)
        self.assertIsInstance(qicon, QIcon)

        qicon_img = ResHandler.get_icon_image(image)
        self.assertIsInstance(qicon_img, QIcon)

        qpixmap = ResHandler.get_image(image)
        self.assertIsInstance(qpixmap, QPixmap)

    def test_res_handler_colored_svg(self):
        import tempfile

        from PySide6.QtCore import QSize

        svg_content = b'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"><circle cx="12" cy="12" r="10"/></svg>'
        with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as f:
            f.write(svg_content)
            temp_svg = f.name

        try:
            icon_fixed = ResIcon(res_id=temp_svg, color=QColor("red"))
            app_theme = AppTheme(ui=UiTheme(primary_color=QColor("blue")))
            qicon_styled = ResHandler.get_icon(icon_fixed, app_theme, theme_style=True, icon_size=32)
            self.assertIsInstance(qicon_styled, QIcon)

            # Without fixed color (has light and dark colors)
            icon_adaptive = ResIcon(res_id=temp_svg, color_light=QColor("blue"), color_dark=QColor("lightblue"))
            # In has_fixed_color(), since color is None and colors are not None, it returns False!
            # ResHandler.__get_icon_color calls theme.ui.get_primary_color()
            qicon_adaptive = ResHandler.get_icon(icon_adaptive, app_theme, theme_style=True, icon_size=24)
            self.assertIsInstance(qicon_adaptive, QIcon)

            direct_icon = ResHandler.colored_svg_icon(temp_svg, QSize(16, 16), QColor("green"))
            self.assertIsInstance(direct_icon, QIcon)
        finally:
            if os.path.exists(temp_svg):
                os.remove(temp_svg)

    def test_project_metadata(self):
        import pylizlib.project as proj

        self.assertEqual(proj.name, "pylizlib")
        self.assertTrue(proj.version)
        self.assertTrue(proj.authors)


if __name__ == "__main__":
    unittest.main()
