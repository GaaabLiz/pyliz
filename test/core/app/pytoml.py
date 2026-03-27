import tempfile
import unittest
from pathlib import Path

from pylizlib.core.app.pytoml import PyProjectToml


class PyProjectTomlTestCase(unittest.TestCase):

    def test_init_raises_for_missing_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_path = Path(temp_dir) / "missing.toml"

            with self.assertRaises(FileNotFoundError):
                PyProjectToml(missing_path)

    def test_extract_info_full_project(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            toml_path = Path(temp_dir) / "pyproject.toml"
            toml_path.write_text(
                """
[project]
name = "demo-app"
version = "1.2.3"
description = "Demo project"
requires-python = ">=3.12"
authors = [
    { name = "Alice", email = "alice@example.com" },
    { name = "Bob", email = "bob@example.com" },
]
""".strip()
                + "\n",
                encoding="utf-8",
            )

            info = PyProjectToml(toml_path).extract_info()

            self.assertEqual(info["name"], "demo-app")
            self.assertEqual(info["version"], "1.2.3")
            self.assertEqual(info["description"], "Demo project")
            self.assertEqual(info["requires_python"], ">=3.12")
            self.assertEqual(info["authors"], [("Alice", "alice@example.com"), ("Bob", "bob@example.com")])

    def test_extract_info_without_project_section(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            toml_path = Path(temp_dir) / "pyproject.toml"
            toml_path.write_text("[tool.demo]\nvalue = 1\n", encoding="utf-8")

            info = PyProjectToml(toml_path).extract_info()

            self.assertIsNone(info["name"])
            self.assertIsNone(info["version"])
            self.assertIsNone(info["description"])
            self.assertIsNone(info["requires_python"])
            self.assertEqual(info["authors"], [])

    def test_extract_info_with_partial_authors(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            toml_path = Path(temp_dir) / "pyproject.toml"
            toml_path.write_text(
                """
[project]
authors = [
    { name = "Alice" },
    { email = "bob@example.com" },
    { }
]
""".strip()
                + "\n",
                encoding="utf-8",
            )

            info = PyProjectToml(toml_path).extract_info()

            self.assertEqual(info["authors"], [("Alice", None), (None, "bob@example.com")])

    def test_gen_project_py_creates_parent_and_writes_content(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            toml_path = Path(temp_dir) / "pyproject.toml"
            toml_path.write_text(
                """
[project]
name = "my-app"
version = "0.1.0"
description = "Simple app"
requires-python = ">=3.12"
authors = [{ name = "Dev", email = "dev@example.com" }]
""".strip()
                + "\n",
                encoding="utf-8",
            )
            output_path = Path(temp_dir) / "generated" / "meta" / "project.py"

            reader = PyProjectToml(toml_path)
            reader.gen_project_py(output_path)

            self.assertTrue(output_path.exists())
            content = output_path.read_text(encoding="utf-8")
            self.assertIn("name = 'my-app'", content)
            self.assertIn("version = '0.1.0'", content)
            self.assertIn("authors = [('Dev', 'dev@example.com')]", content)


if __name__ == "__main__":
    unittest.main()