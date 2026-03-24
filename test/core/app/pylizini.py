import os
import tempfile
import unittest
from unittest.mock import patch

from pylizlib.core.app.pylizapp import PylizApp
from pylizlib.core.app.pylizini import PylizIniHandler, PylizIniItem


class PylizIniHandlerTestCase(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        def fake_home_dir(app_name, create_if_not=True):
            target = os.path.join(self.temp_dir.name, app_name)
            if create_if_not:
                os.makedirs(target, exist_ok=True)
            return target

        self.path_patcher = patch(
            "pylizlib.core.app.pylizapp.pathutils.get_app_home_dir",
            side_effect=fake_home_dir,
        )
        self.path_patcher.start()
        self.addCleanup(self.path_patcher.stop)

        self.app = PylizApp("ConfigApp")
        self.app.create_ini("settings.ini")

    def test_read_requires_explicit_app(self):
        item = PylizIniItem(id="theme", name="Theme", section="general")

        with self.assertRaises(ValueError):
            PylizIniHandler.read(item)

    def test_write_requires_explicit_app(self):
        item = PylizIniItem(id="theme", name="Theme", section="general", default="dark")

        with self.assertRaises(ValueError):
            PylizIniHandler.write(item, "light")

    def test_write_none_without_default_raises(self):
        item = PylizIniItem(id="theme", name="Theme", section="general")

        with self.assertRaises(ValueError):
            PylizIniHandler.write(item, value=None, app=self.app)

    def test_read_use_default_writes_back_to_ini(self):
        item = PylizIniItem(id="theme", name="Theme", section="general", default="dark")

        value = PylizIniHandler.read(item, use_default_if_none=True, app=self.app)

        self.assertEqual(value, "dark")
        self.assertEqual(self.app.get_ini_value("general", "theme"), "dark")

    def test_read_use_empty_if_none_returns_empty_string(self):
        item = PylizIniItem(id="theme", name="Theme", section="general")

        value = PylizIniHandler.read(item, use_empty_if_none=True, app=self.app)

        self.assertEqual(value, "")

    def test_read_prefers_default_over_empty_when_both_enabled(self):
        item = PylizIniItem(id="theme", name="Theme", section="general", default="dark")

        value = PylizIniHandler.read(
            item,
            use_default_if_none=True,
            use_empty_if_none=True,
            app=self.app,
        )

        self.assertEqual(value, "dark")

    def test_read_boolean_value(self):
        item = PylizIniItem(id="enabled", name="Enabled", section="general", is_bool=True)
        self.app.set_ini_value("general", "enabled", True)

        value = PylizIniHandler.read(item, app=self.app)

        self.assertIs(value, True)

    def test_safe_int_read_valid_value(self):
        item = PylizIniItem(id="retries", name="Retries", section="general", default=1)
        self.app.set_ini_value("general", "retries", "42")

        value = PylizIniHandler.safe_int_read(item, app=self.app)

        self.assertEqual(value, 42)

    def test_safe_int_read_invalid_value_returns_default(self):
        item = PylizIniItem(id="retries", name="Retries", section="general", default=3)
        self.app.set_ini_value("general", "retries", "not-a-number")

        value = PylizIniHandler.safe_int_read(item, app=self.app)

        self.assertEqual(value, 3)

    def test_safe_int_read_invalid_default_returns_zero(self):
        item = PylizIniItem(id="retries", name="Retries", section="general", default="bad-default")

        value = PylizIniHandler.safe_int_read(item, app=self.app)

        self.assertEqual(value, 0)

    def test_safe_int_read_missing_without_default_returns_zero(self):
        item = PylizIniItem(id="retries", name="Retries", section="general")

        value = PylizIniHandler.safe_int_read(item, app=self.app)

        self.assertEqual(value, 0)


if __name__ == "__main__":
    unittest.main()