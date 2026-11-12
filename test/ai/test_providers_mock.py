import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
from PIL import Image

from pylizlib.ai.providers import EasyOcrProvider, JoyTagProvider, NudeNetProvider
from pylizlib.media.lizmedia import LizMedia


class ProvidersMockTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="pyliz_ai_prov_")
        self.image_path = Path(self.temp_dir.name) / "test.jpg"
        Image.new("RGB", (32, 32), color=(100, 150, 200)).save(self.image_path)

        self.video_path = Path(self.temp_dir.name) / "test.mp4"
        self.video_path.write_bytes(b"fake_mp4_content")

        self.unsupported_path = Path(self.temp_dir.name) / "test.wav"
        self.unsupported_path.write_bytes(b"RIFFfake_wav_content")

    def tearDown(self):
        self.temp_dir.cleanup()

    # --- JoyTagProvider Tests ---

    def test_joytag_unsupported_media(self):
        prov = JoyTagProvider()
        media = LizMedia(self.unsupported_path)
        res = prov.scan(media)
        self.assertEqual(res.tags, [])

    def test_joytag_missing_dependencies_raises(self):
        prov = JoyTagProvider()
        with patch.dict("sys.modules", {"torch": None}):
            with self.assertRaises(ImportError):
                prov._get_runtime()

    def test_joytag_cached_runtime(self):
        prov = JoyTagProvider()
        prov._model = "dummy_model"
        prov._tag_list = ["t1"]
        prov._device = "cpu"
        prov._tvf = "dummy_tvf"
        prov._torch = "dummy_torch"
        rt = prov._get_runtime()
        self.assertEqual(rt, ("dummy_model", ["t1"], "cpu", "dummy_tvf", "dummy_torch"))

    def test_joytag_scan_image(self):
        prov = JoyTagProvider(confidence_threshold=0.5)
        media = LizMedia(self.image_path)

        mock_model = MagicMock()
        mock_torch = MagicMock()
        mock_tvf = MagicMock()

        with patch.object(prov, "_get_runtime", return_value=(mock_model, ["cat", "dog"], "cpu", mock_tvf, mock_torch)):
            with patch.object(prov, "_predict_from_image", return_value=["cat"]):
                res = prov.scan(media)
                self.assertEqual(res.tags, ["cat"])

    def test_joytag_scan_video(self):
        prov = JoyTagProvider(confidence_threshold=0.5)
        media = LizMedia(self.video_path)

        mock_model = MagicMock()
        mock_torch = MagicMock()
        mock_tvf = MagicMock()
        dummy_frames = [np.zeros((32, 32, 3), dtype=np.uint8)]

        with patch.object(prov, "_get_runtime", return_value=(mock_model, ["sky", "clouds"], "cpu", mock_tvf, mock_torch)):
            with patch("pylizlib.ai.providers.sample_video_frames", return_value=dummy_frames):
                with patch.object(prov, "_predict_from_image", return_value=["sky"]):
                    res = prov.scan(media)
                    self.assertEqual(res.tags, ["sky"])

    def test_joytag_predict_from_image_dict_output(self):
        prov = JoyTagProvider(confidence_threshold=0.4)
        mock_model = MagicMock()
        mock_torch = MagicMock()
        mock_tvf = MagicMock()

        # Mock tensor outputs
        pred_tensor = MagicMock()
        pred_tensor.dim.return_value = 2
        pred_tensor.squeeze.return_value = pred_tensor

        mock_torch.sigmoid.return_value = [0.8, 0.2]  # First above 0.4, second below
        mock_model.return_value = {"tags": pred_tensor}

        img = Image.new("RGB", (10, 10))
        tags = prov._predict_from_image(img, mock_model, ["tag1", "tag2"], "cpu", mock_tvf, mock_torch)
        self.assertEqual(tags, ["tag1"])

    def test_joytag_predict_from_image_tuple_output(self):
        prov = JoyTagProvider(confidence_threshold=0.5)
        mock_model = MagicMock()
        mock_torch = MagicMock()
        mock_tvf = MagicMock()

        pred_tensor = MagicMock()
        pred_tensor.dim.return_value = 1
        mock_torch.sigmoid.return_value = [0.1, 0.9]
        mock_model.return_value = (pred_tensor,)

        img = Image.new("RGB", (10, 10))
        tags = prov._predict_from_image(img, mock_model, ["tag1", "tag2"], "cpu", mock_tvf, mock_torch)
        self.assertEqual(tags, ["tag2"])

    # --- EasyOcrProvider Tests ---

    def test_easyocr_missing_dependencies_raises(self):
        prov = EasyOcrProvider()
        with patch.dict("sys.modules", {"easyocr": None}):
            with self.assertRaises(ImportError):
                prov._get_reader()

    def test_easyocr_cached_reader(self):
        prov = EasyOcrProvider()
        prov._reader = "mock_reader"
        self.assertEqual(prov._get_reader(), "mock_reader")

    def test_easyocr_scan_image(self):
        prov = EasyOcrProvider()
        media = LizMedia(self.image_path)

        mock_reader = MagicMock()
        mock_reader.readtext.return_value = [([0, 0], "INVOICE", 0.99), ([0, 0], "TOTAL $50", 0.95)]

        with patch.object(prov, "_get_reader", return_value=mock_reader):
            res = prov.scan(media)
            self.assertEqual(res.ocr_text, ["INVOICE", "TOTAL $50"])
            self.assertTrue(res.ocr_detected)

    def test_easyocr_scan_video(self):
        prov = EasyOcrProvider()
        media = LizMedia(self.video_path)

        mock_reader = MagicMock()
        mock_reader.readtext.return_value = [([0, 0], "SUBTITLE", 0.88)]
        dummy_frames = [np.zeros((32, 32, 3), dtype=np.uint8)]

        with patch.object(prov, "_get_reader", return_value=mock_reader):
            with patch("pylizlib.ai.providers.sample_video_frames", return_value=dummy_frames):
                res = prov.scan(media)
                self.assertEqual(res.ocr_text, ["SUBTITLE"])
                self.assertTrue(res.ocr_detected)

    def test_easyocr_scan_unsupported_media(self):
        prov = EasyOcrProvider()
        media = LizMedia(self.unsupported_path)
        with patch.object(prov, "_get_reader"):
            res = prov.scan(media)
            self.assertEqual(res.ocr_text, [])
            self.assertFalse(res.ocr_detected)

    def test_easyocr_extract_texts_variations(self):
        raw = [
            ([1, 2], " valid text ", 0.9),
            ([1, 2], "", 0.5),  # empty text
            "not a tuple",  # invalid structure
            ([1, 2], "second valid"),
        ]
        extracted = EasyOcrProvider._extract_texts(raw)
        self.assertEqual(extracted, ["valid text", "second valid"])

    # --- NudeNetProvider Tests ---

    def test_nudenet_missing_dependencies_raises(self):
        prov = NudeNetProvider()
        with patch.dict("sys.modules", {"nudenet": None}):
            with self.assertRaises(ImportError):
                prov._get_detector()

    def test_nudenet_cached_detector(self):
        prov = NudeNetProvider()
        prov._detector = "mock_detector"
        self.assertEqual(prov._get_detector(), "mock_detector")

    def test_nudenet_scan_image_explicit(self):
        prov = NudeNetProvider(inference_threshold=0.5)
        media = LizMedia(self.image_path)

        mock_det = MagicMock()
        mock_det.detect.return_value = [{"class": "FEMALE_BREAST_EXPOSED", "score": 0.85}]

        with patch.object(prov, "_get_detector", return_value=mock_det):
            res = prov.scan(media)
            self.assertTrue(res.nsfw)

    def test_nudenet_scan_image_safe(self):
        prov = NudeNetProvider(inference_threshold=0.5)
        media = LizMedia(self.image_path)

        mock_det = MagicMock()
        mock_det.detect.return_value = [{"class": "FACE_FEMALE", "score": 0.99}]

        with patch.object(prov, "_get_detector", return_value=mock_det):
            res = prov.scan(media)
            self.assertFalse(res.nsfw)

    def test_nudenet_scan_video(self):
        prov = NudeNetProvider(inference_threshold=0.5)
        media = LizMedia(self.video_path)

        mock_det = MagicMock()
        dummy_frames = [np.zeros((16, 16, 3), dtype=np.uint8)]

        with patch.object(prov, "_get_detector", return_value=mock_det):
            with patch("pylizlib.ai.providers.sample_video_frames", return_value=dummy_frames):
                with patch.object(prov, "_detect_frame", return_value=True):
                    res = prov.scan(media)
                    self.assertTrue(res.nsfw)

    def test_nudenet_scan_video_safe(self):
        prov = NudeNetProvider(inference_threshold=0.5)
        media = LizMedia(self.video_path)

        mock_det = MagicMock()
        dummy_frames = [np.zeros((16, 16, 3), dtype=np.uint8)]

        with patch.object(prov, "_get_detector", return_value=mock_det):
            with patch("pylizlib.ai.providers.sample_video_frames", return_value=dummy_frames):
                with patch.object(prov, "_detect_frame", return_value=False):
                    res = prov.scan(media)
                    self.assertFalse(res.nsfw)

    def test_nudenet_scan_unsupported_media(self):
        prov = NudeNetProvider()
        media = LizMedia(self.unsupported_path)
        with patch.object(prov, "_get_detector"):
            res = prov.scan(media)
            self.assertFalse(res.nsfw)

    def test_nudenet_detect_frame(self):
        prov = NudeNetProvider()
        mock_det = MagicMock()
        frame = np.zeros((16, 16, 3), dtype=np.uint8)

        with patch.object(prov, "_detect_image", return_value=True) as mock_detect_img:
            res = prov._detect_frame(mock_det, frame)
            self.assertTrue(res)
            mock_detect_img.assert_called_once()


if __name__ == "__main__":
    unittest.main()
