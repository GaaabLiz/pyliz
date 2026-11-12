import unittest
from unittest.mock import MagicMock, patch

import cv2
import numpy as np

from pylizlib.media.compute.frameselector import (
    AllFrameSelector,
    DynamicFrameSelector,
    UniformFrameSelector,
)
from pylizlib.media.domain.video import FrameOptions, SceneType


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


class DynamicFrameSelectorTestCase(unittest.TestCase):
    @patch("pylizlib.media.compute.frameselector.cv2.VideoCapture")
    def test_select_frames_full_pipeline(self, mock_cap_cls):
        capture = MagicMock()
        capture.isOpened.return_value = True
        capture.get.side_effect = lambda prop: {
            cv2.CAP_PROP_FPS: 10,
            cv2.CAP_PROP_FRAME_COUNT: 4,
            cv2.CAP_PROP_POS_MSEC: 100,
        }.get(prop, 0)

        # 4 frames for _detect_scene_changes, then 2 frames for _extract_frames
        f1 = np.zeros((10, 10, 3), dtype=np.uint8)
        f2 = np.ones((10, 10, 3), dtype=np.uint8) * 200  # large diff -> scene change
        f3 = np.ones((10, 10, 3), dtype=np.uint8) * 200
        f4 = np.zeros((10, 10, 3), dtype=np.uint8)  # large diff -> scene change

        capture.read.side_effect = [
            (True, f1),
            (True, f2),
            (True, f3),
            (True, f4),
            (False, None),  # end of scene detection
            (True, f1),  # extract frame 1
            (True, f2),  # extract frame 2
        ]
        mock_cap_cls.return_value = capture

        selector = DynamicFrameSelector()
        options = FrameOptions(min_frames=2, max_frames=2)
        frames = selector.select_frames("test.mp4", options)

        self.assertEqual(len(frames), 2)
        capture.release.assert_called_once()

    def test_calculate_frame_difference(self):
        selector = DynamicFrameSelector()
        img1 = np.zeros((5, 5, 3), dtype=np.uint8)
        img2 = np.ones((5, 5, 3), dtype=np.uint8) * 100
        diff = selector._calculate_frame_difference(img1, img2)
        self.assertAlmostEqual(diff, 100.0, places=1)


class AllFrameSelectorTestCase(unittest.TestCase):
    @patch("pylizlib.media.compute.frameselector.cv2.VideoCapture")
    def test_select_all_frames(self, mock_cap_cls):
        capture = MagicMock()
        capture.isOpened.return_value = True
        capture.get.side_effect = lambda prop: {
            cv2.CAP_PROP_FPS: 25,
            cv2.CAP_PROP_FRAME_COUNT: 2,
            cv2.CAP_PROP_POS_MSEC: 40.0,
        }.get(prop, 0)

        f1 = np.zeros((4, 4, 3), dtype=np.uint8)
        f2 = np.ones((4, 4, 3), dtype=np.uint8) * 50

        capture.read.side_effect = [
            (True, f1),
            (True, f2),
            (False, None),
        ]
        mock_cap_cls.return_value = capture

        selector = AllFrameSelector()
        options = FrameOptions()
        frames = selector.select_frames("short.mp4", options)

        self.assertEqual(len(frames), 2)
        self.assertEqual(frames[0].timestamp, 0.04)
        capture.release.assert_called_once()


class FrameSelectorTestCase(unittest.TestCase):
    @patch("cv2.VideoCapture")
    def test_validate_video_fails_raises_value_error(self, mock_vc):
        cap = MagicMock()
        cap.isOpened.return_value = False
        mock_vc.return_value = cap

        selector = UniformFrameSelector()
        with self.assertRaises(ValueError):
            selector.select_frames("bad_video.mp4", FrameOptions())

    @patch("cv2.VideoCapture")
    def test_uniform_frame_selector(self, mock_vc):
        cap = MagicMock()
        cap.isOpened.return_value = True

        def mock_get(prop):
            if prop == cv2.CAP_PROP_FPS:
                return 30.0
            if prop == cv2.CAP_PROP_FRAME_COUNT:
                return 150.0  # 5 seconds
            if prop == cv2.CAP_PROP_POS_MSEC:
                return 1000.0
            return 0.0

        cap.get.side_effect = mock_get
        dummy_frame = np.full((16, 16, 3), 120, dtype=np.uint8)
        cap.read.return_value = (True, dummy_frame)
        mock_vc.return_value = cap

        selector = UniformFrameSelector()
        opts = FrameOptions(min_frames=3, max_frames=5)
        frames = selector.select_frames("sample.mp4", opts)

        self.assertTrue(len(frames) >= 3)
        self.assertEqual(frames[0].scene_type, SceneType.STATIC)
        cap.release.assert_called_once()

    @patch("cv2.VideoCapture")
    def test_all_frame_selector(self, mock_vc):
        cap = MagicMock()
        cap.isOpened.return_value = True

        def mock_get(prop):
            if prop == cv2.CAP_PROP_FPS:
                return 10.0
            if prop == cv2.CAP_PROP_FRAME_COUNT:
                return 3.0
            if prop == cv2.CAP_PROP_POS_MSEC:
                return 200.0
            return 0.0

        cap.get.side_effect = mock_get
        dummy_frame = np.zeros((10, 10, 3), dtype=np.uint8)
        cap.read.side_effect = [(True, dummy_frame), (True, dummy_frame), (True, dummy_frame), (False, None)]
        mock_vc.return_value = cap

        selector = AllFrameSelector()
        frames = selector.select_frames("short.mp4", FrameOptions())

        self.assertEqual(len(frames), 3)
        cap.release.assert_called_once()

    @patch("cv2.VideoCapture")
    def test_dynamic_frame_selector(self, mock_vc):
        cap = MagicMock()
        cap.isOpened.return_value = True

        def mock_get(prop):
            if prop == cv2.CAP_PROP_FPS:
                return 30.0
            if prop == cv2.CAP_PROP_FRAME_COUNT:
                return 90.0  # 3 seconds
            if prop == cv2.CAP_PROP_POS_MSEC:
                return 500.0
            return 0.0

        cap.get.side_effect = mock_get

        # Scene detection: frame1 and frame2 with difference > threshold
        f1 = np.zeros((10, 10, 3), dtype=np.uint8)
        f2 = np.full((10, 10, 3), 200, dtype=np.uint8)

        # First pass detects scene changes; second pass extracts frames
        cap.read.side_effect = [
            (True, f1),
            (True, f2),
            (False, None),  # end of detect loop
            (True, f1),
            (True, f2),
            (False, None),  # extraction loop
        ]
        mock_vc.return_value = cap

        selector = DynamicFrameSelector()
        opts = FrameOptions(min_frames=2, max_frames=5)
        frames = selector.select_frames("dynamic.mp4", opts)

        self.assertTrue(len(frames) >= 1)
        cap.release.assert_called_once()
