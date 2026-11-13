import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
from PIL import Image

from pylizlib.core.domain.os import FileType
from pylizlib.media.util.image import (
    ImageUtils,
    load_images_as_ndarrays,
    save_ndarrays_as_images,
)


class SaveAndLoadNdarraysTestCase(unittest.TestCase):
    def test_save_and_load_images(self):
        with tempfile.TemporaryDirectory() as td:
            # Create two dummy RGB numpy images
            img1 = np.zeros((10, 10, 3), dtype=np.uint8)
            img1[0, 0] = [255, 0, 0]
            img2 = np.ones((10, 10, 3), dtype=np.uint8) * 128

            out_dir = os.path.join(td, "frames")
            save_ndarrays_as_images([img1, img2], out_dir, prefix="test", extension="png")

            self.assertTrue(os.path.exists(os.path.join(out_dir, "test_0.png")))
            self.assertTrue(os.path.exists(os.path.join(out_dir, "test_1.png")))

            loaded = load_images_as_ndarrays(out_dir)
            self.assertEqual(len(loaded), 2)
            self.assertEqual(loaded[0].shape, (10, 10, 3))

    def test_load_images_handles_unreadable_file(self):
        with tempfile.TemporaryDirectory() as td:
            # Save one valid image and one non-image text file
            valid_img = Image.new("RGB", (5, 5), color="blue")
            valid_img.save(os.path.join(td, "valid.png"))
            with open(os.path.join(td, "corrupt.png"), "wb") as f:
                f.write(b"not a real image")

            with patch("pylizlib.media.util.image.logger.error") as mock_log:
                loaded = load_images_as_ndarrays(td)
                self.assertEqual(len(loaded), 1)
                mock_log.assert_called_once()


class ImageUtilsTestCase(unittest.TestCase):
    def test_check_file_is_image_not_media(self):
        with patch("pylizlib.media.util.image.is_media_file", return_value=False):
            with self.assertRaisesRegex(ValueError, "not a media file"):
                ImageUtils.check_sd_metadata("doc.txt")

    def test_check_file_is_image_not_image_type(self):
        with patch("pylizlib.media.util.image.is_media_file", return_value=True):
            with patch("pylizlib.media.util.image.get_file_type", return_value=FileType.VIDEO):
                with self.assertRaisesRegex(ValueError, "not an image file"):
                    ImageUtils.check_sd_metadata("clip.mp4")

    @patch("pylizlib.media.util.image.is_media_file", return_value=True)
    @patch("pylizlib.media.util.image.get_file_type", return_value=FileType.IMAGE)
    @patch("pylizlib.media.util.image.ParserManager")
    def test_check_sd_metadata_found(self, mock_pm_cls, _mock_ft, _mock_mf):
        mock_pm = MagicMock()
        mock_prompt_info = SimpleNamespace(prompt="a photograph of a cat", model="v1-5")
        mock_pm.parse.return_value = mock_prompt_info
        mock_pm_cls.return_value = mock_pm

        result = ImageUtils.check_sd_metadata("sample.png")
        self.assertIs(result, mock_prompt_info)

    @patch("pylizlib.media.util.image.is_media_file", return_value=True)
    @patch("pylizlib.media.util.image.get_file_type", return_value=FileType.IMAGE)
    @patch("pylizlib.media.util.image.ParserManager")
    def test_check_sd_metadata_none_or_exception(self, mock_pm_cls, _mock_ft, _mock_mf):
        mock_pm = MagicMock()
        mock_pm.parse.return_value = None
        mock_pm_cls.return_value = mock_pm

        self.assertIsNone(ImageUtils.check_sd_metadata("plain.png"))

        mock_pm.parse.side_effect = RuntimeError("parser error")
        with patch("pylizlib.media.util.image.logger.error") as mock_log:
            self.assertIsNone(ImageUtils.check_sd_metadata("broken.png"))
            mock_log.assert_called_once()


class ImageUtilsTestCaseExpandedTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="pyliz_image_util_")
        self.base_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_save_and_load_ndarrays(self):
        arr1 = np.full((20, 20, 3), 50, dtype=np.uint8)
        arr2 = np.full((20, 20, 3), 150, dtype=np.uint8)

        out_folder = self.base_dir / "saved_frames"
        save_ndarrays_as_images([arr1, arr2], str(out_folder), prefix="test_frame", extension="png")

        self.assertTrue((out_folder / "test_frame_0.png").exists())
        self.assertTrue((out_folder / "test_frame_1.png").exists())

        loaded = load_images_as_ndarrays(str(out_folder))
        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded[0].shape, (20, 20, 3))

    def test_load_images_handles_read_errors(self):
        out_folder = self.base_dir / "corrupted"
        out_folder.mkdir()
        (out_folder / "bad.png").write_text("not an image")

        loaded = load_images_as_ndarrays(str(out_folder))
        self.assertEqual(loaded, [])

    def test_check_file_is_image_validations(self):
        # Non-media file
        txt_file = self.base_dir / "notes.txt"
        txt_file.write_text("hello")
        with self.assertRaises(ValueError):
            ImageUtils.check_sd_metadata(str(txt_file))

        # Valid image file but non-SD metadata
        img_file = self.base_dir / "sample.png"
        Image.new("RGB", (10, 10), color="blue").save(img_file)
        meta = ImageUtils.check_sd_metadata(str(img_file))
        self.assertIsNone(meta)

    @patch("pylizlib.media.util.image.ParserManager")
    def test_check_sd_metadata_success_and_exception(self, mock_pm_cls):
        img_file = self.base_dir / "sample_sd.png"
        Image.new("RGB", (10, 10), color="green").save(img_file)

        mock_pm = MagicMock()
        mock_info = MagicMock()
        mock_pm.parse.return_value = mock_info
        mock_pm_cls.return_value = mock_pm

        res = ImageUtils.check_sd_metadata(str(img_file))
        self.assertEqual(res, mock_info)

        # Exception handling
        mock_pm.parse.side_effect = Exception("parse error")
        res_err = ImageUtils.check_sd_metadata(str(img_file))
        self.assertIsNone(res_err)
