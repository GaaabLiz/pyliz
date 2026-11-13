import tomllib
import unittest
from pathlib import Path


class OptionalDependenciesTestCase(unittest.TestCase):
    def test_ai_extras_declare_media_import_requirements(self):
        project_root = Path(__file__).resolve().parents[3]
        pyproject = tomllib.loads((project_root / "pyproject.toml").read_text(encoding="utf-8"))
        project = pyproject["project"]
        extras = project["optional-dependencies"]
        required = {"exifread", "ffmpeg-python", "sd-parsers"}

        self.assertIn("pydantic", {requirement.split(">", 1)[0].strip() for requirement in project["dependencies"]})
        for extra_name, requirements in extras.items():
            with self.subTest(extra=extra_name):
                package_names = {requirement.split(">", 1)[0].split("=", 1)[0].split(";", 1)[0].strip() for requirement in requirements}
                self.assertNotIn("pydantic", package_names)

        for extra_name in ("ai", "ai-linux-nvidia"):
            with self.subTest(extra=extra_name):
                package_names = {requirement.split(">", 1)[0].split("=", 1)[0].split(";", 1)[0].strip() for requirement in extras[extra_name]}
                self.assertTrue(required <= package_names, f"Missing from {extra_name}: {required - package_names}")

        self.assertEqual(extras["ai-macos"], ["pylizlib[ai]"])


if __name__ == "__main__":
    unittest.main()
