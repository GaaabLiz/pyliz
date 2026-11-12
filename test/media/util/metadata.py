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


class MetadataHandlerTestCaseExpandedTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="pyliz_metadata_test_")
        self.base_dir = Path(self.temp_dir.name)
        self.sample_img = self.base_dir / "sample.jpg"
        self.sample_img.write_bytes(b"dummy image bytes")

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch("shutil.which", return_value=None)
    def test_exiftool_missing_returns_false(self, _):
        handler = MetadataHandler(self.sample_img)
        self.assertFalse(handler.generate_xmp(self.base_dir / "out.xmp"))
        self.assertFalse(handler.append_eagle_to_xmp(MagicMock(), self.base_dir / "out.xmp"))
        self.assertIsNone(handler.get_image_creation_date())

    @patch("subprocess.run")
    @patch("shutil.which", return_value="/usr/bin/exiftool")
    def test_generate_xmp_success(self, _, mock_run):
        mock_run.return_value = MagicMock()
        handler = MetadataHandler(self.sample_img)
        out_xmp = self.base_dir / "sample.xmp"
        self.assertTrue(handler.generate_xmp(out_xmp))
        mock_run.assert_called_once()

    @patch("subprocess.run")
    @patch("shutil.which", return_value="/usr/bin/exiftool")
    def test_generate_xmp_nothing_to_write_fallback(self, _, mock_run):
        err = subprocess.CalledProcessError(1, cmd="exiftool", stderr="Error: Nothing to write")
        mock_run.side_effect = err

        handler = MetadataHandler(self.sample_img)
        out_xmp = self.base_dir / "sample.xmp"
        self.assertTrue(handler.generate_xmp(out_xmp))
        self.assertTrue(out_xmp.exists())
        self.assertIn("xmpmeta", out_xmp.read_text())

    @patch("subprocess.run")
    @patch("shutil.which", return_value="/usr/bin/exiftool")
    def test_generate_xmp_failure(self, _, mock_run):
        err = subprocess.CalledProcessError(1, cmd="exiftool", stderr="Fatal error")
        mock_run.side_effect = err

        handler = MetadataHandler(self.sample_img)
        self.assertFalse(handler.generate_xmp(self.base_dir / "out.xmp"))

    @patch("shutil.which", return_value="/usr/bin/exiftool")
    def test_append_eagle_to_xmp_missing_file(self, _):
        handler = MetadataHandler(self.sample_img)
        self.assertFalse(handler.append_eagle_to_xmp(MagicMock(), self.base_dir / "missing.xmp"))

    @patch("subprocess.run")
    @patch("shutil.which", return_value="/usr/bin/exiftool")
    def test_append_eagle_to_xmp_empty_metadata(self, _, mock_run):
        xmp_file = self.base_dir / "exists.xmp"
        xmp_file.write_text("<xmp></xmp>")

        meta = MagicMock()
        meta.tags = []
        meta.annotation = None

        handler = MetadataHandler(self.sample_img)
        self.assertTrue(handler.append_eagle_to_xmp(meta, xmp_file))
        mock_run.assert_not_called()

    @patch("subprocess.run")
    @patch("shutil.which", return_value="/usr/bin/exiftool")
    def test_append_eagle_to_xmp_success_and_error(self, _, mock_run):
        xmp_file = self.base_dir / "exists.xmp"
        xmp_file.write_text("<xmp></xmp>")

        meta = MagicMock()
        meta.tags = ["nature", "forest"]
        meta.annotation = "A beautiful photo"

        handler = MetadataHandler(self.sample_img)
        self.assertTrue(handler.append_eagle_to_xmp(meta, xmp_file))
        mock_run.assert_called_once()

        # CalledProcessError handling
        mock_run.side_effect = subprocess.CalledProcessError(1, "exiftool", stderr="Write error")
        self.assertFalse(handler.append_eagle_to_xmp(meta, xmp_file))

    @patch("subprocess.run")
    def test_set_creation_date(self, mock_run):
        xmp_file = self.base_dir / "exists.xmp"
        xmp_file.write_text("<xmp></xmp>")

        handler = MetadataHandler(self.sample_img)
        target_date = datetime(2024, 6, 15, 12, 30, 45)

        # File exists -> success
        self.assertTrue(handler.set_creation_date(target_date, xmp_file))
        mock_run.assert_called_once()

        # File does not exist -> False
        self.assertFalse(handler.set_creation_date(target_date, self.base_dir / "missing.xmp"))

        # Exception handling
        mock_run.side_effect = Exception("error")
        self.assertFalse(handler.set_creation_date(target_date, xmp_file))

    @patch("subprocess.run")
    @patch("shutil.which", return_value="/usr/bin/exiftool")
    def test_get_image_creation_date(self, _, mock_run):
        mock_proc = MagicMock()
        mock_proc.stdout = "2023:05:10 14:20:00\n"
        mock_run.return_value = mock_proc

        handler = MetadataHandler(self.sample_img)
        dt = handler.get_image_creation_date()
        self.assertEqual(dt, datetime(2023, 5, 10, 14, 20, 0))

        # Output with invalid date
        mock_proc.stdout = "invalid:date:format\n"
        self.assertIsNone(handler.get_image_creation_date())

        # Exception handling
        mock_run.side_effect = Exception("failed")
        self.assertIsNone(handler.get_image_creation_date())
