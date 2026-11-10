import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pylizlib.core.app.configini import CfgPath, IniItem, IniManager


class IniManagerTestCase(unittest.TestCase):
    def test_create_writes_empty_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            ini_path = os.path.join(temp_dir, "empty.ini")

            manager = IniManager(ini_path)
            manager.create()

            self.assertTrue(os.path.isfile(ini_path))

    def test_create_and_read_items(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            ini_path = os.path.join(temp_dir, "settings.ini")

            manager = IniManager(ini_path)
            manager.create(
                [
                    IniItem("general", "theme", "dark"),
                    IniItem("general", "enabled", True),
                    IniItem("general", "retries", 3),
                ]
            )

            self.assertEqual(manager.read("general", "theme"), "dark")
            self.assertIs(manager.read("general", "enabled", is_bool=True), True)
            self.assertEqual(manager.read("general", "retries"), "3")

    def test_read_missing_file_returns_none(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = IniManager(os.path.join(temp_dir, "missing.ini"))

            self.assertIsNone(manager.read("general", "theme"))

    def test_read_missing_section_or_key_returns_none(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            ini_path = os.path.join(temp_dir, "settings.ini")
            manager = IniManager(ini_path)
            manager.create([IniItem("general", "theme", "dark")])

            self.assertIsNone(manager.read("missing", "theme"))
            self.assertIsNone(manager.read("general", "missing"))

    def test_read_invalid_boolean_returns_none(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            ini_path = os.path.join(temp_dir, "settings.ini")
            manager = IniManager(ini_path)
            manager.create([IniItem("general", "enabled", "maybe")])

            self.assertIsNone(manager.read("general", "enabled", is_bool=True))

    def test_write_creates_parent_directories(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            ini_path = os.path.join(temp_dir, "nested", "config", "settings.ini")
            manager = IniManager(ini_path)

            manager.write("general", "theme", "light")

            self.assertTrue(os.path.isfile(ini_path))
            self.assertEqual(manager.read("general", "theme"), "light")

    @patch("pylizlib.core.app.configini.os.replace", side_effect=OSError("replace failed"))
    def test_failed_atomic_write_preserves_existing_configuration(self, _mock_replace):
        with tempfile.TemporaryDirectory() as temp_dir:
            ini_path = os.path.join(temp_dir, "settings.ini")
            manager = IniManager(ini_path)
            manager.create([IniItem("general", "theme", "dark")])
            previous = Path(ini_path).read_text(encoding="utf-8")

            with self.assertRaisesRegex(OSError, "replace failed"):
                manager.write("general", "theme", "light")

            self.assertEqual(Path(ini_path).read_text(encoding="utf-8"), previous)
            self.assertEqual(os.listdir(temp_dir), ["settings.ini"])

    def test_malformed_configuration_is_reported_as_missing_value(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            ini_path = os.path.join(temp_dir, "settings.ini")
            Path(ini_path).write_text("[general\ntheme=dark\n", encoding="utf-8")

            self.assertIsNone(IniManager(ini_path).read("general", "theme"))

    def test_percent_values_round_trip_without_interpolation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            ini_path = os.path.join(temp_dir, "settings.ini")
            manager = IniManager(ini_path)
            values = {"single": "%", "escaped": "%20", "reference": "%(other)s"}

            manager.create([IniItem("general", key, value) for key, value in values.items()])
            for key, expected in values.items():
                with self.subTest(key=key):
                    self.assertEqual(manager.read("general", key), expected)

            manager.write("general", "written", "%25")
            self.assertEqual(manager.read("general", "written"), "%25")


class CfgPathTestCase(unittest.TestCase):
    def test_check_duplicates_prints_sections_and_keys(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = IniManager(os.path.join(temp_dir, "settings.ini"))
            manager.create([IniItem("general", "theme", "dark")])

            with patch("pylizlib.core.app.configini.rich.print") as mock_print:
                CfgPath(Path(temp_dir)).check_duplicates(keys=True, sections=True)

            self.assertGreaterEqual(mock_print.call_count, 2)


if __name__ == "__main__":
    unittest.main()
