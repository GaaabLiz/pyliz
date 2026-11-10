import tomllib
import unittest
from pathlib import Path


class OptionalDependenciesTestCase(unittest.TestCase):
    def test_ai_extras_declare_media_import_requirements(self):
        project_root = Path(__file__).resolve().parents[2]
        pyproject = tomllib.loads((project_root / "pyproject.toml").read_text(encoding="utf-8"))
        extras = pyproject["project"]["optional-dependencies"]
        required = {"exifread", "ffmpeg-python", "sd-parsers"}

        for extra_name in ("ai", "ai-macos", "ai-linux-nvidia"):
            with self.subTest(extra=extra_name):
                requirements = extras[extra_name]
                package_names = {requirement.split(">", 1)[0].split("=", 1)[0].split(";", 1)[0].strip() for requirement in requirements}
                self.assertTrue(required <= package_names, f"Missing from {extra_name}: {required - package_names}")


if __name__ == "__main__":
    unittest.main()
