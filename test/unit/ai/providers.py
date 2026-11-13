import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
from PIL import Image

from pylizlib.ai.providers import JoyTagProvider, NudeNetProvider


class JoyTagProviderSecurityTestCase(unittest.TestCase):
    def test_model_and_executable_definition_use_immutable_revisions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            model_dir = Path(temp_dir)
            model_path = model_dir / "model"
            model_path.mkdir()
            (model_path / "top_tags.txt").write_text("tag\n", encoding="utf-8")
            code_path = model_dir / "Models.py"
            code_path.write_text(
                "class Model:\n    def eval(self): return self\n    def to(self, device): return self\nclass VisionModel:\n    @staticmethod\n    def load_model(path): return Model()\n",
                encoding="utf-8",
            )

            torch = types.ModuleType("torch")
            torch.cuda = types.SimpleNamespace(is_available=lambda: False)
            torch.backends = types.SimpleNamespace(mps=types.SimpleNamespace(is_available=lambda: False))
            torch.device = lambda name: name

            torchvision = types.ModuleType("torchvision")
            torchvision.__path__ = []
            transforms = types.ModuleType("torchvision.transforms")
            transforms.__path__ = []
            functional = types.ModuleType("torchvision.transforms.functional")
            torchvision.transforms = transforms
            transforms.functional = functional

            hub = types.ModuleType("huggingface_hub")
            snapshot_download = MagicMock(return_value=str(model_path))
            hf_hub_download = MagicMock(return_value=str(code_path))
            hub.snapshot_download = snapshot_download
            hub.hf_hub_download = hf_hub_download

            with patch.dict(
                sys.modules,
                {
                    "torch": torch,
                    "torchvision": torchvision,
                    "torchvision.transforms": transforms,
                    "torchvision.transforms.functional": functional,
                    "huggingface_hub": hub,
                },
            ):
                provider = JoyTagProvider(model_dir=temp_dir)
                model, _, device, _, _ = provider._get_runtime()

            self.assertEqual(device, "cpu")
            self.assertIsNotNone(model)
            self.assertEqual(snapshot_download.call_args.kwargs["revision"], "6b7f16331a6ccf0fdce37d5a9564715f6e772b22")
            self.assertEqual(hf_hub_download.call_args.kwargs["revision"], "df9e86f69b37ede2560de24503c18ac199e9b3f0")
            self.assertEqual(hf_hub_download.call_args.kwargs["repo_type"], "space")


class NudeNetVideoSamplingTestCase(unittest.TestCase):
    def setUp(self):
        self.media = types.SimpleNamespace(is_image=False, is_video=True, path=Path("sample.mp4"))

    def test_video_with_no_sampled_frames_has_unknown_nsfw_result(self):
        provider = NudeNetProvider()
        detector = MagicMock()
        provider._get_detector = MagicMock(return_value=detector)

        with patch("pylizlib.ai.providers.sample_video_frames_with_count", return_value=([], 0)):
            result = provider.scan(self.media)

        self.assertIsNone(result.nsfw)
        self.assertEqual(result.nsfw_frames_analyzed, 0)
        self.assertFalse(result.nsfw_analysis_complete)
        detector.detect.assert_not_called()

    def test_video_with_partial_samples_is_not_reported_as_safe(self):
        provider = NudeNetProvider()
        provider._get_detector = MagicMock(return_value=object())
        sampled_frames = [object(), object()]

        with (
            patch("pylizlib.ai.providers.sample_video_frames_with_count", return_value=(sampled_frames, 3)),
            patch.object(provider, "_detect_frame", return_value=False) as detect_frame,
        ):
            result = provider.scan(self.media)

        self.assertIsNone(result.nsfw)
        self.assertEqual(result.nsfw_frames_analyzed, 2)
        self.assertFalse(result.nsfw_analysis_complete)
        self.assertEqual(detect_frame.call_count, 2)

    def test_complete_negative_video_scan_reports_false_and_full_coverage(self):
        provider = NudeNetProvider()
        provider._get_detector = MagicMock(return_value=object())
        sampled_frames = [object(), object()]

        with (
            patch("pylizlib.ai.providers.sample_video_frames_with_count", return_value=(sampled_frames, 2)),
            patch.object(provider, "_detect_frame", return_value=False) as detect_frame,
        ):
            result = provider.scan(self.media)

        self.assertFalse(result.nsfw)
        self.assertEqual(result.nsfw_frames_analyzed, 2)
        self.assertTrue(result.nsfw_analysis_complete)
        self.assertEqual(detect_frame.call_count, 2)


class NudeNetTemporaryFrameTestCase(unittest.TestCase):
    def test_frame_file_is_closed_readable_and_removed_after_detection(self):
        provider = NudeNetProvider()
        detector = MagicMock()
        observed = {}

        def inspect_image(path):
            observed["path"] = Path(path)
            observed["exists_during_detection"] = Path(path).is_file()
            with Image.open(path) as image:
                observed["size"] = image.size
            return []

        detector.detect.side_effect = inspect_image
        before = set(Path(tempfile.gettempdir()).glob("pyliz_nudenet_*"))

        result = provider._detect_frame(detector, np.zeros((3, 4, 3), dtype=np.uint8))

        after = set(Path(tempfile.gettempdir()).glob("pyliz_nudenet_*"))
        self.assertFalse(result)
        self.assertTrue(observed["exists_during_detection"])
        self.assertEqual(observed["size"], (4, 3))
        self.assertFalse(observed["path"].exists())
        self.assertEqual(after, before)

    def test_frame_file_is_removed_when_detection_raises(self):
        provider = NudeNetProvider()
        detector = MagicMock()
        detector.detect.side_effect = OSError("detector failed")
        before = set(Path(tempfile.gettempdir()).glob("pyliz_nudenet_*"))

        with self.assertRaisesRegex(OSError, "detector failed"):
            provider._detect_frame(detector, np.zeros((2, 2, 3), dtype=np.uint8))

        self.assertEqual(set(Path(tempfile.gettempdir()).glob("pyliz_nudenet_*")), before)


if __name__ == "__main__":
    unittest.main()
