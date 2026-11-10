import unittest
from unittest.mock import MagicMock, patch

import cv2
import numpy as np

from pylizlib.media.compute.frameselector import UniformFrameSelector
from pylizlib.media.domain.video import FrameOptions


class UniformFrameSelectorLoggerTestCase(unittest.TestCase):
    @patch("pylizlib.media.compute.frameselector.cv2.VideoCapture")
    def test_select_frames_works_with_the_configured_standard_logger(self, mock_video_capture):
        capture = mock_video_capture.return_value
        capture.isOpened.return_value = True
        capture.get.side_effect = lambda prop: {
            cv2.CAP_PROP_FPS: 30,
            cv2.CAP_PROP_FRAME_COUNT: 1,
            cv2.CAP_PROP_POS_MSEC: 0,
        }[prop]
        capture.read.side_effect = [(True, np.zeros((2, 2, 3), dtype=np.uint8))]

        frames = UniformFrameSelector().select_frames(
            "sample.mp4",
            FrameOptions(frames_per_minute=1, min_frames=1, max_frames=1),
        )

        self.assertEqual(len(frames), 1)
        capture.release.assert_called_once()


class FrameSelectorValidationTestCase(unittest.TestCase):
    def test_invalid_fps_values_raise_and_release_capture(self):
        for fps in (0, -1, float("nan"), float("inf")):
            with self.subTest(fps=fps):
                capture = MagicMock()
                capture.isOpened.return_value = True
                capture.get.side_effect = lambda prop: fps if prop == cv2.CAP_PROP_FPS else 10
                with patch("pylizlib.media.compute.frameselector.cv2.VideoCapture", return_value=capture):
                    with self.assertRaisesRegex(ValueError, "Invalid video FPS"):
                        UniformFrameSelector()._validate_video("invalid-fps.mp4")
                    capture.release.assert_called_once()

    def test_uniform_selection_clamps_to_available_distinct_indices(self):
        selector = UniformFrameSelector()
        capture = MagicMock()
        capture.isOpened.return_value = True
        capture.get.side_effect = lambda prop: {
            cv2.CAP_PROP_FPS: 30,
            cv2.CAP_PROP_FRAME_COUNT: 2,
            cv2.CAP_PROP_POS_MSEC: 0,
        }[prop]
        capture.read.side_effect = [
            (True, np.zeros((2, 2, 3), dtype=np.uint8)),
            (True, np.ones((2, 2, 3), dtype=np.uint8)),
        ]
        with patch("pylizlib.media.compute.frameselector.cv2.VideoCapture", return_value=capture):
            frames = selector.select_frames("short.mp4", FrameOptions(min_frames=10, max_frames=10))

        positions = [call.args[1] for call in capture.set.call_args_list]
        self.assertEqual(len(frames), 2)
        self.assertEqual(positions, [0, 1])
        capture.release.assert_called_once()

    def test_dynamic_selection_supports_a_single_frame(self):
        from pylizlib.media.compute.frameselector import DynamicFrameSelector

        selector = DynamicFrameSelector()
        capture = MagicMock()
        capture.get.return_value = 4
        capture.read.return_value = (True, np.zeros((2, 2, 3), dtype=np.uint8))

        frames = selector._extract_frames(capture, target_frames=1, scene_changes=[])

        self.assertEqual(len(frames), 1)
        capture.set.assert_called_once_with(cv2.CAP_PROP_POS_FRAMES, 0)

    def test_zero_frame_metadata_returns_empty_and_releases_capture(self):
        capture = MagicMock()
        capture.isOpened.return_value = True
        capture.get.side_effect = lambda prop: 30 if prop == cv2.CAP_PROP_FPS else 0
        with patch("pylizlib.media.compute.frameselector.cv2.VideoCapture", return_value=capture):
            frames = UniformFrameSelector().select_frames("empty.mp4", FrameOptions())

        self.assertEqual(frames, [])
        capture.read.assert_not_called()
        capture.release.assert_called_once()

    def test_capture_is_released_when_frame_read_raises(self):
        capture = MagicMock()
        capture.isOpened.return_value = True
        capture.get.side_effect = lambda prop: 30 if prop == cv2.CAP_PROP_FPS else 1
        capture.read.side_effect = OSError("decode failed")
        with patch("pylizlib.media.compute.frameselector.cv2.VideoCapture", return_value=capture):
            with self.assertRaisesRegex(OSError, "decode failed"):
                UniformFrameSelector().select_frames(
                    "broken.mp4",
                    FrameOptions(frames_per_minute=1, min_frames=1, max_frames=1),
                )

        capture.release.assert_called_once()


if __name__ == "__main__":
    unittest.main()
