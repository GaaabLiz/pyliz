import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from PySide6.QtCore import QSize
from PySide6.QtGui import QColor

from pylizlib.core.domain.os import OsTheme
from pylizlib.qt.domain.resource import ResIcon
from pylizlib.qt.handler.resource import ResHandler


class ResHandlerColorTestCase(unittest.TestCase):
    def make_theme(self, mode, primary):
        return SimpleNamespace(system_ui_mode=mode, ui=SimpleNamespace(get_primary_color=lambda: primary))

    def resolve_color(self, icon, theme):
        with patch.object(ResHandler, "colored_svg_icon", return_value="rendered") as render:
            result = ResHandler.get_icon(icon, theme, theme_style=True)
        self.assertEqual(result, "rendered")
        return render.call_args.args[2]

    def test_missing_overrides_use_theme_primary_color(self):
        primary = QColor("red")
        icon = ResIcon(":/icon.svg")

        resolved = self.resolve_color(icon, self.make_theme(OsTheme.LIGHT, primary))

        self.assertEqual(resolved, primary)
        self.assertFalse(icon.has_fixed_color())

    def test_light_and_dark_overrides_resolve_by_theme(self):
        light = QColor("white")
        dark = QColor("black")
        icon = ResIcon(":/icon.svg", color_light=light, color_dark=dark)

        self.assertEqual(self.resolve_color(icon, self.make_theme(OsTheme.LIGHT, QColor("red"))), light)
        self.assertEqual(self.resolve_color(icon, self.make_theme(OsTheme.DARK, QColor("red"))), dark)

    def test_single_override_uses_theme_color_for_the_other_mode(self):
        light = QColor("white")
        primary = QColor("blue")
        icon = ResIcon(":/icon.svg", color_light=light)

        self.assertEqual(self.resolve_color(icon, self.make_theme(OsTheme.LIGHT, primary)), light)
        self.assertEqual(self.resolve_color(icon, self.make_theme(OsTheme.DARK, primary)), primary)

    def test_invalid_theme_color_falls_back_to_valid_black(self):
        resolved = self.resolve_color(ResIcon(":/icon.svg"), self.make_theme(OsTheme.UNKNOWN, None))

        self.assertTrue(resolved.isValid())
        self.assertEqual(resolved, QColor("black"))

    def test_painter_is_closed_when_rendering_raises(self):
        painter = MagicMock()
        pixmap = MagicMock()
        renderer = MagicMock()
        renderer.render.side_effect = RuntimeError("render failed")

        with (
            patch("pylizlib.qt.handler.resource.QSvgRenderer", return_value=renderer),
            patch("pylizlib.qt.handler.resource.QPixmap", return_value=pixmap),
            patch("pylizlib.qt.handler.resource.QPainter", return_value=painter),
        ):
            with self.assertRaisesRegex(RuntimeError, "render failed"):
                ResHandler.colored_svg_icon(":/icon.svg", QSize(16, 16), QColor("red"))

        painter.end.assert_called_once()


if __name__ == "__main__":
    unittest.main()
