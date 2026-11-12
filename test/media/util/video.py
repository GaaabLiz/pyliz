import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import numpy as np

from pylizlib.media.domain.video import Frame, SceneType
from pylizlib.media.util.video import VideoUtils


class VideoUtilsTestCase(unittest.TestCase):
    @patch("pylizlib.media.util.video.ffmpeg")
    def test_extract_audio_skips_when_use_existing(self, mock_ffmpeg):
        with tempfile.TemporaryDirectory() as td:
            audio_path = os.path.join(td, "audio.mp3")
            with open(audio_path, "w") as f:
                f.write("existing audio")

            VideoUtils.extract_audio("video.mp4", audio_path, use_existing=True)
            mock_ffmpeg.input.assert_not_called()

    @patch("pylizlib.media.util.video.ffmpeg")
    def test_extract_audio_runs_ffmpeg(self, mock_ffmpeg):
        mock_pipeline = MagicMock()
        mock_ffmpeg.input.return_value.output.return_value = mock_pipeline

        VideoUtils.extract_audio("video.mp4", "out.mp3", use_existing=False)
        mock_ffmpeg.input.assert_called_once_with("video.mp4")
        mock_ffmpeg.input.return_value.output.assert_called_once_with("out.mp3")
        mock_pipeline.run.assert_called_once_with(overwrite_output=True)

    @patch("pylizlib.media.util.video.save_ndarrays_as_images")
    def test_extract_frame_advanced(self, mock_save):
        mock_selector = MagicMock()
        dummy_frame = Frame(image=np.zeros((10, 10, 3), dtype=np.uint8), timestamp=1.5, scene_type=SceneType.STATIC)
        mock_selector.select_frames.return_value = [dummy_frame]

        result = VideoUtils.extract_frame_advanced("video.mp4", "frames_dir", mock_selector)
        self.assertEqual(len(result), 1)
        mock_selector.select_frames.assert_called_once()
        mock_save.assert_called_once()

    def test_extract_frames_thr_skips_if_folder_not_empty(self):
        with tempfile.TemporaryDirectory() as td:
            video_file = os.path.join(td, "test.mp4")
            with open(video_file, "w") as f:
                f.write("data")

            out_dir = os.path.join(td, "out")
            os.makedirs(out_dir)
            with open(os.path.join(out_dir, "frame_0.jpg"), "w") as f:
                f.write("image")

            with patch("pylizlib.media.util.video.cv2.VideoCapture") as mock_cap:
                VideoUtils.extract_frames_thr(video_file, out_dir, use_existing=True)
                mock_cap.assert_not_called()

    @patch("pylizlib.media.util.video.cv2.VideoCapture")
    def test_extract_frames_thr_first_frame_read_failure(self, mock_cap_cls):
        with tempfile.TemporaryDirectory() as td:
            video_file = os.path.join(td, "test.mp4")
            with open(video_file, "w") as f:
                f.write("data")
            out_dir = os.path.join(td, "out")

            mock_cap = MagicMock()
            mock_cap.read.return_value = (False, None)
            mock_cap_cls.return_value = mock_cap

            with self.assertRaisesRegex(Exception, "OpenCV error: Error reading video"):
                VideoUtils.extract_frames_thr(video_file, out_dir, use_existing=False)

    @patch("pylizlib.media.util.video.cv2.VideoCapture")
    def test_extract_frames_thr_success_saves_differing_frames(self, mock_cap_cls):
        with tempfile.TemporaryDirectory() as td:
            video_file = os.path.join(td, "clip.mp4")
            with open(video_file, "w") as f:
                f.write("data")
            out_dir = os.path.join(td, "out")

            frame1 = np.zeros((20, 20, 3), dtype=np.uint8)
            frame2 = np.zeros((20, 20, 3), dtype=np.uint8)  # identical, should be skipped
            frame3 = np.ones((20, 20, 3), dtype=np.uint8) * 255  # different, threshold exceeded

            mock_cap = MagicMock()
            mock_cap.isOpened.side_effect = [True, True, True, False]
            mock_cap.read.side_effect = [
                (True, frame1),  # initial frame
                (True, frame2),  # loop 1
                (True, frame3),  # loop 2
                (False, None),  # loop 3 exit
            ]
            mock_cap_cls.return_value = mock_cap

            VideoUtils.extract_frames_thr(video_file, out_dir, difference_threshold=50, use_existing=False)
            files = os.listdir(out_dir)
            # Should have frame 0 (initial) and frame 1 (from frame3 exceeding threshold)
            self.assertEqual(len(files), 2)

    @patch("pylizlib.media.util.video.ffmpeg.probe")
    def test_get_video_creation_date(self, mock_probe):
        # 1. ISO format date
        mock_probe.return_value = {"format": {"tags": {"creation_time": "2024-06-15T10:00:00Z"}}}
        ts = VideoUtils.get_video_creation_date("vid.mp4")
        self.assertIsNotNone(ts)

        # 2. Apple format date takes priority
        mock_probe.return_value = {
            "format": {
                "tags": {
                    "com.apple.quicktime.creationdate": "2024-06-16T12:00:00+00:00",
                    "creation_time": "2024-06-15T10:00:00Z",
                }
            }
        }
        ts_apple = VideoUtils.get_video_creation_date("vid.mp4")
        self.assertIsNotNone(ts_apple)
        self.assertNotEqual(ts, ts_apple)

        # 3. Invalid date or exception
        mock_probe.return_value = {"format": {"tags": {"creation_time": "invalid"}}}
        self.assertIsNone(VideoUtils.get_video_creation_date("vid.mp4"))

        mock_probe.side_effect = Exception("probe failed")
        self.assertIsNone(VideoUtils.get_video_creation_date("vid.mp4"))

    @patch("pylizlib.media.util.video.ffmpeg.probe")
    def test_get_video_duration_seconds(self, mock_probe):
        mock_probe.return_value = {"format": {"duration": "123.45"}}
        duration = VideoUtils.get_video_duration_seconds("vid.mp4")
        self.assertEqual(duration, 123.45)

        mock_probe.side_effect = Exception("error")
        self.assertIsNone(VideoUtils.get_video_duration_seconds("vid.mp4"))

    @patch("pylizlib.media.util.video.cv2.VideoCapture")
    def test_get_video_frame_rate(self, mock_cap_cls):
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.return_value = 29.97
        mock_cap_cls.return_value = mock_cap

        fps = VideoUtils.get_video_frame_rate("vid.mp4")
        self.assertEqual(fps, 29.97)

        # Not opened
        mock_cap.isOpened.return_value = False
        self.assertIsNone(VideoUtils.get_video_frame_rate("vid.mp4"))

        # Exception
        mock_cap_cls.side_effect = Exception("error")
        self.assertIsNone(VideoUtils.get_video_frame_rate("vid.mp4"))


from pathlib import Path

from pylizlib.media.domain.video import FrameOptions


class VideoUtilsTestCaseExpandedTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="pyliz_video_util_")
        self.base_dir = Path(self.temp_dir.name)
        self.dummy_video = self.base_dir / "sample.mp4"
        self.dummy_video.write_bytes(b"dummy video bytes")

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch("ffmpeg.input")
    def test_extract_audio(self, mock_input):
        audio_out = self.base_dir / "out.mp3"
        mock_output = MagicMock()
        mock_input.return_value.output.return_value = mock_output

        VideoUtils.extract_audio(str(self.dummy_video), str(audio_out))
        mock_input.assert_called_once_with(str(self.dummy_video))
        mock_output.run.assert_called_once_with(overwrite_output=True)

        # use_existing when file exists
        audio_out.write_bytes(b"audio")
        mock_input.reset_mock()
        VideoUtils.extract_audio(str(self.dummy_video), str(audio_out), use_existing=True)
        mock_input.assert_not_called()

    @patch("pylizlib.media.util.video.save_ndarrays_as_images")
    def test_extract_frame_advanced(self, mock_save):
        mock_selector = MagicMock()
        dummy_frame = Frame(
            image=np.zeros((10, 10, 3), dtype=np.uint8),
            timestamp=0.0,
            scene_type=SceneType.STATIC,
        )
        mock_selector.select_frames.return_value = [dummy_frame]

        frame_folder = self.base_dir / "frames"
        frames = VideoUtils.extract_frame_advanced(
            str(self.dummy_video),
            str(frame_folder),
            mock_selector,
            FrameOptions(),
        )

        self.assertEqual(len(frames), 1)
        mock_selector.select_frames.assert_called_once()
        mock_save.assert_called_once()

    @patch("cv2.VideoCapture")
    def test_extract_frames_thr(self, mock_vc):
        cap = MagicMock()
        cap.isOpened.side_effect = [True, True, False]
        # Frame 1 and Frame 2
        f1 = np.full((10, 10, 3), 10, dtype=np.uint8)
        f2 = np.full((10, 10, 3), 100, dtype=np.uint8)
        cap.read.side_effect = [(True, f1), (True, f2), (False, None)]
        mock_vc.return_value = cap

        out_folder = self.base_dir / "thr_frames"
        VideoUtils.extract_frames_thr(
            str(self.dummy_video),
            str(out_folder),
            difference_threshold=20,
            use_existing=False,
        )

        cap.release.assert_called_once()

    @patch("cv2.VideoCapture")
    def test_extract_frames_thr_first_read_fails(self, mock_vc):
        cap = MagicMock()
        cap.read.return_value = (False, None)
        mock_vc.return_value = cap

        out_folder = self.base_dir / "thr_fail"
        with self.assertRaises(Exception):
            VideoUtils.extract_frames_thr(str(self.dummy_video), str(out_folder))

    def test_extract_frames_thr_skips_if_existing(self):
        out_folder = self.base_dir / "thr_existing"
        out_folder.mkdir()
        (out_folder / "existing.jpg").write_text("x")

        with patch("cv2.VideoCapture") as mock_vc:
            VideoUtils.extract_frames_thr(
                str(self.dummy_video),
                str(out_folder),
                use_existing=True,
            )
            mock_vc.assert_not_called()

    @patch("ffmpeg.probe")
    def test_get_video_creation_date(self, mock_probe):
        # ISO date with Z
        mock_probe.return_value = {"format": {"tags": {"creation_time": "2023-01-01T12:00:00Z"}}}
        ts = VideoUtils.get_video_creation_date(str(self.dummy_video))
        self.assertIsNotNone(ts)

        # Exception handling
        mock_probe.side_effect = Exception("probe failed")
        self.assertIsNone(VideoUtils.get_video_creation_date(str(self.dummy_video)))

    @patch("ffmpeg.probe")
    def test_get_video_duration_seconds(self, mock_probe):
        mock_probe.return_value = {"format": {"duration": "12.34"}}
        duration = VideoUtils.get_video_duration_seconds(str(self.dummy_video))
        self.assertAlmostEqual(duration, 12.34)

        mock_probe.side_effect = Exception("failed")
        self.assertIsNone(VideoUtils.get_video_duration_seconds(str(self.dummy_video)))

    @patch("cv2.VideoCapture")
    def test_get_video_frame_rate(self, mock_vc):
        cap = MagicMock()
        cap.isOpened.return_value = True
        cap.get.return_value = 29.97
        mock_vc.return_value = cap

        fps = VideoUtils.get_video_frame_rate(str(self.dummy_video))
        self.assertAlmostEqual(fps, 29.97)

        # Video not opened
        cap.isOpened.return_value = False
        self.assertIsNone(VideoUtils.get_video_frame_rate(str(self.dummy_video)))

        # Exception handling
        mock_vc.side_effect = Exception("opencv error")
        self.assertIsNone(VideoUtils.get_video_frame_rate(str(self.dummy_video)))
