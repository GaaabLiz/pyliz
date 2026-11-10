import unittest
from unittest.mock import patch

import cv2

from pylizlib.media.compute.video_sampling import sample_video_frames_with_count


class SampleVideoFramesWithCountTestCase(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
