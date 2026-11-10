import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

from pylizlib.qt.scripts import exec_gen_qrc


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


if __name__ == "__main__":
    unittest.main()
