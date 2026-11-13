import unittest
from unittest.mock import MagicMock, patch

import cv2
import numpy as np

from pylizlib.media.compute.video_sampling import (
    _build_frame_indices,
    sample_video_frames,
    sample_video_frames_with_count,
)


class SampleVideoFramesWithCountTestCase(unittest.TestCase):
    def test_indices_cover_full_range_at_even_intervals(self):
        indices = _build_frame_indices(total_frames=11, max_frames=5)

        self.assertEqual(indices, [0, 3, 5, 8, 10])
        self.assertEqual(len(indices), len(set(indices)))

    def test_single_frame_sample_uses_first_frame(self):
        self.assertEqual(_build_frame_indices(total_frames=10, max_frames=1), [0])

    def test_non_positive_sample_count_is_rejected(self):
        for max_frames in (0, -1):
            with self.subTest(max_frames=max_frames), self.assertRaisesRegex(ValueError, "max_frames"):
                _build_frame_indices(total_frames=10, max_frames=max_frames)

    @patch("pylizlib.media.compute.video_sampling.cv2.VideoCapture")
    def test_zero_frame_video_reports_no_sampled_frames(self, mock_video_capture):
        capture = mock_video_capture.return_value
        capture.isOpened.return_value = True
        capture.get.return_value = 0

        frames, expected_count = sample_video_frames_with_count("empty.mp4")

        self.assertEqual(frames, [])
        self.assertEqual(expected_count, 0)
        capture.release.assert_called_once()

    @patch("pylizlib.media.compute.video_sampling.cv2.VideoCapture")
    def test_unreadable_samples_are_reported_as_an_incomplete_attempt(self, mock_video_capture):
        capture = mock_video_capture.return_value
        capture.isOpened.return_value = True
        capture.get.side_effect = lambda prop: 10 if prop == cv2.CAP_PROP_FRAME_COUNT else 0
        capture.read.return_value = (False, None)

        frames, expected_count = sample_video_frames_with_count("unreadable.mp4", max_frames=5)

        self.assertEqual(frames, [])
        self.assertEqual(expected_count, 5)
        self.assertEqual(capture.read.call_count, 5)
        capture.release.assert_called_once()


class VideoSamplingTestCase(unittest.TestCase):
    def test_build_frame_indices_less_or_equal(self):
        self.assertEqual(_build_frame_indices(total_frames=3, max_frames=5), [0, 1, 2])
        self.assertEqual(_build_frame_indices(total_frames=5, max_frames=5), [0, 1, 2, 3, 4])

    def test_build_frame_indices_greater(self):
        indices = _build_frame_indices(total_frames=100, max_frames=5)
        self.assertEqual(len(indices), 5)
        self.assertEqual(indices[0], 0)
        self.assertEqual(indices[-1], 99)

    @patch("cv2.VideoCapture")
    def test_sample_video_frames_cannot_open_raises(self, mock_vc):
        cap = MagicMock()
        cap.isOpened.return_value = False
        mock_vc.return_value = cap

        with self.assertRaises(ValueError):
            sample_video_frames("/fake/path.mp4")

    @patch("cv2.VideoCapture")
    def test_sample_video_frames_zero_frames(self, mock_vc):
        cap = MagicMock()
        cap.isOpened.return_value = True
        cap.get.return_value = 0
        mock_vc.return_value = cap

        frames = sample_video_frames("/fake/path.mp4")
        self.assertEqual(frames, [])
        cap.release.assert_called_once()

    @patch("cv2.VideoCapture")
    def test_sample_video_frames_success(self, mock_vc):
        cap = MagicMock()
        cap.isOpened.return_value = True
        cap.get.return_value = 10
        dummy_bgr = np.zeros((10, 10, 3), dtype=np.uint8)
        dummy_bgr[0, 0, 0] = 255  # Blue in BGR -> Red in RGB
        cap.read.return_value = (True, dummy_bgr)
        mock_vc.return_value = cap

        frames = sample_video_frames("/fake/path.mp4", max_frames=3)
        self.assertEqual(len(frames), 3)
        self.assertEqual(frames[0].shape, (10, 10, 3))
        # Verify BGR to RGB conversion
        self.assertEqual(frames[0][0, 0, 2], 255)
        cap.release.assert_called_once()
