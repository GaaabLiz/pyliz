import subprocess
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pylizlib.media.util.metadata import MetadataHandler


class MetadataHandlerTestCase(unittest.TestCase):
    def test_generate_xmp_exiftool_missing(self):
        handler = MetadataHandler("sample.jpg")
        with patch("pylizlib.media.util.metadata.shutil.which", return_value=None):
            self.assertFalse(handler.generate_xmp("sample.xmp"))

    @patch("pylizlib.media.util.metadata.shutil.which", return_value="/usr/local/bin/exiftool")
    @patch("pylizlib.media.util.metadata.subprocess.run")
    def test_generate_xmp_success(self, mock_run, _mock_which):
        handler = MetadataHandler("sample.jpg")
        self.assertTrue(handler.generate_xmp("sample.xmp"))
        mock_run.assert_called_once()

    @patch("pylizlib.media.util.metadata.shutil.which", return_value="/usr/local/bin/exiftool")
    @patch("pylizlib.media.util.metadata.subprocess.run")
    def test_generate_xmp_nothing_to_write_minimal_xmp(self, mock_run, _mock_which):
        handler = MetadataHandler("sample.jpg")
        err = subprocess.CalledProcessError(1, ["exiftool"], stderr="Error: Nothing to write")
        mock_run.side_effect = err

        with tempfile.TemporaryDirectory() as td:
            output_xmp = Path(td) / "minimal.xmp"
            result = handler.generate_xmp(output_xmp)
            self.assertTrue(result)
            self.assertTrue(output_xmp.exists())
            self.assertIn("x:xmpmeta", output_xmp.read_text(encoding="utf-8"))

    @patch("pylizlib.media.util.metadata.shutil.which", return_value="/usr/local/bin/exiftool")
    @patch("pylizlib.media.util.metadata.subprocess.run")
    def test_generate_xmp_failure(self, mock_run, _mock_which):
        handler = MetadataHandler("sample.jpg")
        mock_run.side_effect = subprocess.CalledProcessError(1, ["exiftool"], stderr="Other error")
        self.assertFalse(handler.generate_xmp("sample.xmp"))

        mock_run.side_effect = OSError("command failure")
        self.assertFalse(handler.generate_xmp("sample.xmp"))

    def test_append_eagle_to_xmp_missing_exiftool_or_file(self):
        handler = MetadataHandler("sample.jpg")
        with patch("pylizlib.media.util.metadata.shutil.which", return_value=None):
            self.assertFalse(handler.append_eagle_to_xmp(SimpleNamespace(tags=[], annotation=""), "nonexistent.xmp"))

        with patch("pylizlib.media.util.metadata.shutil.which", return_value="/usr/local/bin/exiftool"):
            self.assertFalse(handler.append_eagle_to_xmp(SimpleNamespace(tags=[], annotation=""), "nonexistent.xmp"))

    @patch("pylizlib.media.util.metadata.shutil.which", return_value="/usr/local/bin/exiftool")
    def test_append_eagle_to_xmp_no_changes(self, _mock_which):
        handler = MetadataHandler("sample.jpg")
        with tempfile.TemporaryDirectory() as td:
            xmp = Path(td) / "file.xmp"
            xmp.write_text("<xmp/>", encoding="utf-8")
            metadata = SimpleNamespace(tags=None, annotation=None)
            self.assertTrue(handler.append_eagle_to_xmp(metadata, xmp))

    @patch("pylizlib.media.util.metadata.shutil.which", return_value="/usr/local/bin/exiftool")
    @patch("pylizlib.media.util.metadata.subprocess.run")
    def test_append_eagle_to_xmp_with_tags_and_annotation(self, mock_run, _mock_which):
        handler = MetadataHandler("sample.jpg")
        with tempfile.TemporaryDirectory() as td:
            xmp = Path(td) / "file.xmp"
            xmp.write_text("<xmp/>", encoding="utf-8")
            metadata = SimpleNamespace(tags=["nature", "landscape"], annotation="Beautiful view")

            self.assertTrue(handler.append_eagle_to_xmp(metadata, xmp))
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            self.assertIn("-xmp:subject+=nature", args)
            self.assertIn("-xmp:subject+=landscape", args)
            self.assertIn("-xmp:description=Beautiful view", args)

    def test_set_creation_date(self):
        handler = MetadataHandler("sample.jpg")
        dt = datetime(2025, 5, 10, 12, 30, 45)

        # non-existent file
        self.assertFalse(handler.set_creation_date(dt, "missing.xmp"))

        # existing file
        with tempfile.TemporaryDirectory() as td:
            xmp = Path(td) / "file.xmp"
            xmp.write_text("<xmp/>", encoding="utf-8")
            with patch("pylizlib.media.util.metadata.subprocess.run") as mock_run:
                self.assertTrue(handler.set_creation_date(dt, xmp))
                mock_run.assert_called_once()

    def test_get_image_creation_date(self):
        handler = MetadataHandler("sample.jpg")

        # Exiftool not installed
        with patch("pylizlib.media.util.metadata.shutil.which", return_value=None):
            self.assertIsNone(handler.get_image_creation_date())

        # Exiftool success
        with patch("pylizlib.media.util.metadata.shutil.which", return_value="/usr/bin/exiftool"):
            mock_res = MagicMock()
            mock_res.stdout = "2024:12:01 10:15:20\n"
            with patch("pylizlib.media.util.metadata.subprocess.run", return_value=mock_res):
                date = handler.get_image_creation_date()
                self.assertEqual(date, datetime(2024, 12, 1, 10, 15, 20))

            # Exiftool output invalid
            mock_res.stdout = "invalid-date\n"
            with patch("pylizlib.media.util.metadata.subprocess.run", return_value=mock_res):
                self.assertIsNone(handler.get_image_creation_date())

            # Exiftool raises
            with patch("pylizlib.media.util.metadata.subprocess.run", side_effect=OSError("run error")):
                self.assertIsNone(handler.get_image_creation_date())


if __name__ == "__main__":
    unittest.main()
