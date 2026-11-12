import shutil

import subprocess

import sys

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
            self.assertEqual(generated_path, 'assets/icons & "symbols"/logo & café.svg')
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
                '</qresource><qresource prefix="quoted&quot;&quot;&quot;">'
                "<file>assets/dark-theme.svg</file></qresource></RCC>",
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
            self.assertIn("class quoted:", source)

    def test_resource_ids_match_qt_aliases_and_empty_prefix(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            assets = root / "assets"
            assets.mkdir()
            (assets / "physical-logo.svg").write_text("<svg />", encoding="utf-8")
            (assets / "physical-root.svg").write_text("<svg />", encoding="utf-8")
            qrc_path = root / "resources.qrc"
            qrc_path.write_text(
                '<RCC><qresource prefix="/icons"><file alias="logo.svg">assets/physical-logo.svg</file></qresource><qresource><file alias="root.svg">assets/physical-root.svg</file></qresource></RCC>',
                encoding="utf-8",
            )
            output_path = root / "resource_ids.py"
            exec_gen_res_py(qrc_path, output_path)
            namespace = {}
            exec(compile(output_path.read_text(encoding="utf-8"), str(output_path), "exec"), namespace)
            resource_ids = namespace["ResourcesIds"]
            logo_id = resource_ids.icons.LOGO
            root_id = resource_ids.Root.ROOT

            rcc_command = Path(sys.executable).parent / "pyside6-rcc"
            if not rcc_command.exists():
                rcc_command = Path(shutil.which("pyside6-rcc") or "")
            if not rcc_command.is_file():
                self.skipTest("pyside6-rcc is not installed")
            binary_path = root / "resources.rcc"
            subprocess.run(
                [str(rcc_command), "--binary", "-o", str(binary_path), str(qrc_path)],
                check=True,
                capture_output=True,
                text=True,
            )

            from PySide6.QtCore import QFile, QResource

            self.assertTrue(QResource.registerResource(str(binary_path)))
            try:
                self.assertTrue(QFile.exists(logo_id))
                self.assertTrue(QFile.exists(root_id))
            finally:
                QResource.unregisterResource(str(binary_path))

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

class QtScriptsTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="pyliz_qt_scripts_")
        self.base_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_exec_gen_qrc(self):
        # Create resource directories with files
        img_dir = self.base_dir / "icons"
        img_dir.mkdir()
        (img_dir / "app.png").write_bytes(b"dummy_png")
        sub_dir = img_dir / "nav"
        sub_dir.mkdir()
        (sub_dir / "back.svg").write_bytes(b"dummy_svg")

        qrc_path = self.base_dir / "resources.qrc"
        exec_gen_qrc(qrc_path, [img_dir])

        self.assertTrue(qrc_path.exists())
        content = qrc_path.read_text(encoding="utf-8")
        self.assertIn("<RCC>", content)
        self.assertIn('prefix="icons"', content)
        self.assertIn("<file>icons/app.png</file>", content)
        self.assertIn("<file>icons/nav/back.svg</file>", content)
        self.assertIn("</RCC>", content)

    def test_exec_gen_res_py(self):
        qrc_content = """<RCC>
  <qresource prefix="icons">
    <file>icons/app.png</file>
    <file>icons/folder-open.svg</file>
  </qresource>
</RCC>"""
        qrc_path = self.base_dir / "test.qrc"
        qrc_path.write_text(qrc_content, encoding="utf-8")

        output_py = self.base_dir / "resources_ids.py"
        exec_gen_res_py(qrc_path, output_py, main_class_name="AppResources")

        self.assertTrue(output_py.exists())
        content = output_py.read_text(encoding="utf-8")
        self.assertIn("class AppResources:", content)
        self.assertIn("class Icons:", content)
        self.assertIn('APP_PNG = ":icons/icons/app.png"', content)
        self.assertIn('FOLDER_OPEN_SVG = ":icons/icons/folder-open.svg"', content)

    def test_exec_gen_css_py(self):
        css_dir = self.base_dir / "styles"
        css_dir.mkdir()
        (css_dir / "dark.css").write_text("body { background: #000; }", encoding="utf-8")
        (css_dir / "light.css").write_text("body { background: #fff; }", encoding="utf-8")

        output_py = self.base_dir / "css_theme.py"
        exec_gen_css_py(css_dir, output_py)

        self.assertTrue(output_py.exists())
        content = output_py.read_text(encoding="utf-8")
        self.assertIn("# AUTOGENERATED", content)
        self.assertIn("dark = r'''body { background: #000; }'''", content)
        self.assertIn("light = r'''body { background: #fff; }'''", content)

    def test_exec_gen_css_py_invalid_dir_raises(self):
        invalid_path = self.base_dir / "nonexistent"
        out = self.base_dir / "out.py"
        with self.assertRaises(ValueError):
            exec_gen_css_py(invalid_path, out)
