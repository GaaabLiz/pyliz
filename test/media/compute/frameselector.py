import unittest
from unittest.mock import patch

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


if __name__ == "__main__":
    unittest.main()
