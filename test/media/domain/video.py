import unittest

import numpy as np

from pylizlib.media.domain.video import Frame, FrameOptions, SceneType


class VideoDomainTestCase(unittest.TestCase):
    def test_frame_dataclass(self):
        dummy_img = np.zeros((10, 10, 3), dtype=np.uint8)
        frame = Frame(
            image=dummy_img,
            timestamp=1.5,
            scene_type=SceneType.STATIC,
            difference_score=12.5,
        )
        self.assertEqual(frame.timestamp, 1.5)
        self.assertEqual(frame.scene_type, SceneType.STATIC)
        self.assertEqual(frame.difference_score, 12.5)
        self.assertEqual(frame.image.shape, (10, 10, 3))

    def test_frame_options_calculate_dynamic_frame_count(self):
        opts = FrameOptions(frames_per_minute=6.0, min_frames=2, max_frames=30)

        # Zero duration
        count_zero = opts.calculate_dynamic_frame_count(0, [])
        self.assertEqual(count_zero, 2)  # clamped to min_frames

        # Normal 60s video with moderate scene changes
        count_norm = opts.calculate_dynamic_frame_count(60.0, [10.0, 20.0, 30.0])
        self.assertTrue(2 <= count_norm <= 30)

        # High scene changes clamping to max_frames
        many_changes = [float(i) for i in range(100)]
        count_high = opts.calculate_dynamic_frame_count(600.0, many_changes)
        self.assertEqual(count_high, 30)  # clamped to max_frames

    def test_frame_options_calculate_uniform_frame_count(self):
        opts = FrameOptions(frames_per_minute=6.0, min_frames=3, max_frames=20)

        # Short video: 10 seconds -> base_frames = 1 -> clamped to min_frames = 3
        count_short = opts.calculate_uniform_frame_count(10.0)
        self.assertEqual(count_short, 3)

        # Long video: 1000 seconds -> base_frames = 100 -> clamped to max_frames = 20
        count_long = opts.calculate_uniform_frame_count(1000.0)
        self.assertEqual(count_long, 20)

        # Moderate video: 120 seconds -> base_frames = 12
        count_mid = opts.calculate_uniform_frame_count(120.0)
        self.assertEqual(count_mid, 12)


if __name__ == "__main__":
    unittest.main()
