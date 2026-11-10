import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

from pylizlib.qt.scripts import exec_gen_css_py, exec_gen_qrc, exec_gen_res_py


class GenerateQrcTestCase(unittest.TestCase):
    def test_escapes_names_and_resolves_files_from_qrc_directory(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            asset_dir = root / "assets" / 'icons & "symbols"'
            asset_dir.mkdir(parents=True)
            asset = asset_dir / "logo & café.svg"
            asset.write_text("<svg />", encoding="utf-8")
            qrc_path = root / "resources.qrc"

            exec_gen_qrc(qrc_path, [asset_dir])

            resource = ET.parse(qrc_path).getroot().find("qresource")
            self.assertEqual(resource.get("prefix"), asset_dir.name)
            generated_path = resource.findtext("file")
            self.assertEqual(generated_path, "assets/icons & \"symbols\"/logo & café.svg")
            self.assertTrue((qrc_path.parent / generated_path).is_file())

    def test_invalid_xml_character_does_not_replace_existing_qrc(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            assets = root / "assets"
            assets.mkdir()
            (assets / "bad\x01.svg").write_text("<svg />", encoding="utf-8")
            qrc_path = root / "resources.qrc"
            qrc_path.write_text("existing qrc", encoding="utf-8")

            with self.assertRaises(ET.ParseError):
                exec_gen_qrc(qrc_path, [assets])

            self.assertEqual(qrc_path.read_text(encoding="utf-8"), "existing qrc")

    def test_resource_module_uses_valid_unique_identifiers(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            qrc_path = root / "resources.qrc"
            qrc_path.write_text(
                '<RCC><qresource prefix="/icons">'
                "<file>assets/dark-theme.svg</file>"
                "<file>assets/dark theme.png</file>"
                "<file>assets/1-logo.svg</file>"
                "</qresource></RCC>",
                encoding="utf-8",
            )
            output_path = root / "resource_ids.py"

            exec_gen_res_py(qrc_path, output_path)

            source = output_path.read_text(encoding="utf-8")
            compile(source, str(output_path), "exec")
            self.assertIn("class icons:", source)
            self.assertIn("DARK_THEME =", source)
            self.assertIn("DARK_THEME_2 =", source)
            self.assertIn("_1_LOGO =", source)

    def test_css_module_safely_quotes_content_and_resolves_name_collisions(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            css_folder = root / "css"
            css_folder.mkdir()
            hyphenated_css = "button { content: '''special'''; }"
            spaced_css = ".other { color: red; }"
            (css_folder / "dark-theme.css").write_text(hyphenated_css, encoding="utf-8")
            (css_folder / "dark theme.css").write_text(spaced_css, encoding="utf-8")
            output_path = root / "styles.py"

            exec_gen_css_py(css_folder, output_path)

            source = output_path.read_text(encoding="utf-8")
            namespace = {}
            exec(compile(source, str(output_path), "exec"), namespace)
            self.assertEqual(namespace["dark_theme"], spaced_css)
            self.assertEqual(namespace["dark_theme_2"], hyphenated_css)


if __name__ == "__main__":
    unittest.main()
