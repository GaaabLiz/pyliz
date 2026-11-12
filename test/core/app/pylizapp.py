import os
import tempfile
import unittest
from unittest.mock import patch

from pylizlib.core.app.configini import IniItem
from pylizlib.core.app.pylizapp import PylizApp, PylizDirFoldersTemplate


class PylizAppTestCase(unittest.TestCase):
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

    def create_app(self, name="TestApp"):
        return PylizApp(name)

    def test_initialization_creates_local_path(self):
        app = self.create_app("ExampleApp")

        self.assertTrue(os.path.isdir(app.get_path()))
        self.assertEqual(app.get_path(), os.path.join(self.temp_dir.name, "ExampleApp"))

    def test_folder_registry_is_per_instance(self):
        first = self.create_app("FirstApp")
        second = self.create_app("SecondApp")

        first.add_folder("cache", "cache")

        self.assertIsNotNone(first.get_folder_path("cache"))
        self.assertIsNone(second.get_folder_path("cache"))

    def test_add_folder_updates_existing_key(self):
        app = self.create_app()

        first_path = app.add_folder("models", "models")
        second_path = app.add_folder("models", "models-v2")

        self.assertTrue(os.path.isdir(first_path))
        self.assertTrue(os.path.isdir(second_path))
        self.assertEqual(app.get_folder_path("models"), second_path)

    def test_get_folder_template_path_without_autocreate_returns_none(self):
        app = self.create_app()

        result = app.get_folder_template_path(PylizDirFoldersTemplate.RESULTS, add_if_not_exist=False)

        self.assertIsNone(result)

    def test_add_all_template_folders_creates_all_directories(self):
        app = self.create_app()

        paths = app.add_all_template_folders()

        self.assertEqual(len(paths), len(PylizDirFoldersTemplate))
        for template in PylizDirFoldersTemplate:
            path = app.get_folder_template_path(template, add_if_not_exist=False)
            self.assertIsNotNone(path)
            self.assertTrue(os.path.isdir(path))

    def test_create_ini_with_items_and_roundtrip_values(self):
        app = self.create_app()
        app.create_ini(
            "settings.ini",
            [
                IniItem("general", "theme", "light"),
                IniItem("general", "enabled", True),
            ],
        )

        self.assertEqual(app.get_ini_value("general", "theme"), "light")
        self.assertIs(app.get_ini_value("general", "enabled", is_bool=True), True)

    def test_failed_ini_creation_does_not_publish_initialized_path(self):
        app = self.create_app()

        with patch("pylizlib.core.app.configini.os.replace", side_effect=OSError("cannot create INI")):
            with self.assertRaisesRegex(OSError, "cannot create INI"):
                app.create_ini("settings.ini")

        self.assertIsNone(app.get_ini_path())
        with self.assertRaises(RuntimeError):
            app.get_ini_value("general", "theme")

        ini_path = app.create_ini("valid.ini")
        self.assertTrue(os.path.isfile(ini_path))
        self.assertEqual(app.get_ini_path(), ini_path)

    def test_set_get_ini_before_create_raises(self):
        app = self.create_app()

        with self.assertRaises(RuntimeError):
            app.get_ini_value("general", "theme")
        with self.assertRaises(RuntimeError):
            app.set_ini_value("general", "theme", "light")

    def test_add_folder_with_ini_requires_initialized_ini(self):
        app = self.create_app()

        with self.assertRaises(RuntimeError):
            app.add_folder_with_ini("models", "models", "paths", "models_dir")

    def test_external_ini_deletion_is_detected(self):
        app = self.create_app()
        ini_path = app.create_ini("settings.ini")
        os.remove(ini_path)

        with self.assertRaises(RuntimeError):
            app.get_ini_value("general", "theme")

    def test_delete_ini_resets_state(self):
        app = self.create_app()
        ini_path = app.create_ini("settings.ini")

        app.delete_ini()

        self.assertFalse(os.path.exists(ini_path))
        self.assertIsNone(app.get_ini_path())
        with self.assertRaises(RuntimeError):
            app.get_ini_value("general", "theme")

    def test_add_folder_with_ini_success(self):
        app = self.create_app()
        app.create_ini("settings.ini")
        folder = app.add_folder_with_ini("cache", "cache_dir", "paths", "cache")
        self.assertTrue(os.path.isdir(folder))
        self.assertEqual(app.get_ini_value("paths", "cache"), folder)

    def test_get_folder_template_path_autocreate(self):
        app = self.create_app()
        path = app.get_folder_template_path(PylizDirFoldersTemplate.RESULTS, add_if_not_exist=True)
        self.assertIsNotNone(path)
        self.assertTrue(os.path.isdir(path))

    def test_create_ini_file_not_found_raises_oserror(self):
        app = self.create_app()
        with patch("pylizlib.core.app.pylizapp.os.path.isfile", return_value=False):
            with self.assertRaises(OSError):
                app.create_ini("settings.ini")

    def test_delete_ini_uninitialized_logs_warning(self):
        app = self.create_app()
        with patch("pylizlib.core.app.pylizapp.logger.warning") as mock_log:
            app.delete_ini()
            mock_log.assert_called_once_with("INI file is not initialized. Nothing to delete.")

    def test_print_hw(self):
        app = self.create_app()
        with patch("builtins.print") as mock_print:
            app.print_hw()
            mock_print.assert_called_once_with("Hello from PylizApp!")


if __name__ == "__main__":
    unittest.main()
