import math
from abc import ABC, abstractmethod
from typing import Any, List, Tuple

import cv2
import numpy as np
from numpy import floating

from pylizlib.core.log.pylizLogger import logger
from pylizlib.media.domain.video import Frame, FrameOptions, SceneType


class FrameSelector(ABC):
    """
    Abstract base class for video frame selection strategies.
    Implementations of this class define how to choose specific frames from a video
    based on different criteria (e.g., scene changes, uniform intervals).
    """

    def __init__(self):
        self.logger = logger

    @abstractmethod
    def select_frames(self, video_path: str, frame_options: FrameOptions) -> List[Frame]:
        """
        Selects a subset of frames from the given video file.

        Args:
            video_path: Path to the video file.
            frame_options: Configuration options for frame selection (counts, thresholds).

        Returns:
            A list of Frame objects containing imagery and metadata.
        """
        pass

    def _validate_video(self, video_path: str) -> Tuple[cv2.VideoCapture, float, float, int]:
        """
        Validates the video file and retrieves its core properties.

        Args:
            video_path: Path to the video file.

        Returns:
            A tuple containing (cv2.VideoCapture, FPS, Duration, Total Frames).

        Raises:
            ValueError: If the video file cannot be opened.
        """
        self.logger.debug(f"Validating video file: {video_path}")
        cap = cv2.VideoCapture(video_path)

        try:
            if not cap.isOpened():
                raise ValueError(f"Failed to open video file: {video_path}")

            fps = float(cap.get(cv2.CAP_PROP_FPS))
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if not math.isfinite(fps) or fps <= 0:
                raise ValueError(f"Invalid video FPS for {video_path}: {fps}")
            if total_frames < 0:
                raise ValueError(f"Invalid frame count for {video_path}: {total_frames}")
            duration = total_frames / fps
        except Exception:
            cap.release()
            raise

        self.logger.debug(f"Video properties - FPS: {fps}, Total frames: {total_frames}, Duration: {duration:.2f}s")
        return cap, fps, duration, total_frames

    def _extract_indexed_frames(
        self,
        cap: cv2.VideoCapture,
        target_frames: int,
        *,
        scene_changes: List[float] | None = None,
        log_indices: bool = False,
    ) -> List[Frame]:
        """Read evenly spaced frames, optionally marking detected transitions.

        Args:
            cap (cv2.VideoCapture): Open video capture positioned for random access.
            target_frames (int): Requested number of frames; clamped to the available frame count.
            scene_changes (List[float] | None): Transition timestamps used to label sampled frames.
            log_indices (bool): Whether to log the selected source frame indices.

        Returns:
            List[Frame]: Successfully decoded frames in RGB order, with timestamps and scene labels.
        """
        total_frames = max(0, int(cap.get(cv2.CAP_PROP_FRAME_COUNT)))
        target_frames = min(max(target_frames, 0), total_frames)
        if target_frames == 0:
            return []

        frame_indices = np.linspace(0, total_frames - 1, num=target_frames, dtype=int)
        if log_indices:
            self.logger.debug(f"Frame indices selected: {frame_indices.tolist()}")

        frames = []
        for frame_index in frame_indices:
            frame_index = int(frame_index)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ret, frame = cap.read()
            if not ret:
                self.logger.warning(f"Failed to read frame at position {frame_index}")
                continue

            timestamp = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            is_transition = any(abs(change - timestamp) < 0.1 for change in scene_changes or ())
            scene_type = SceneType.TRANSITION if is_transition else SceneType.STATIC
            frames.append(Frame(image=frame_rgb, timestamp=timestamp, scene_type=scene_type))

        return frames


class DynamicFrameSelector(FrameSelector):
    """
    Dynamic frame selection strategy that identifies scene changes and motion
    to pick the most representative frames from a video.
    """

    def select_frames(self, video_path: str, frame_options: FrameOptions) -> List[Frame]:
        """
        Statically analyzes the video to detect scene changes and extracts frames
        accordingly, weighted by scene transitions.
        """
        self.logger.debug("Starting dynamic frame selection")
        cap, fps, duration, total_frames = self._validate_video(video_path)

        try:
            scene_changes = self._detect_scene_changes(video_path, cap)
            target_frames = frame_options.calculate_dynamic_frame_count(duration, scene_changes)

            self.logger.debug(f"Target frames for analysis: {target_frames}")
            frames = self._extract_frames(cap, target_frames, scene_changes)
        finally:
            cap.release()
        self.logger.debug(f"Dynamic frame selection completed. Selected {len(frames)} frames")
        return frames

    def _detect_scene_changes(
        self,
        video_path: str,
        cap: cv2.VideoCapture,
        threshold: float = 20.0,
    ) -> List[float]:
        """
        Iterates through the video to identify timestamps where significant pixel
        differences occur between consecutive frames.

        Args:
            video_path: Path to the video.
            cap: Opened cv2.VideoCapture instance.
            threshold: Sensitivity threshold for scene change detection.

        Returns:
            List of timestamps (seconds) where scene changes were detected.
        """
        self.logger.debug("Detecting scene changes")
        scene_changes = []
        prev_frame = None

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            if prev_frame is not None:
                diff_score = self._calculate_frame_difference(prev_frame, frame)

                if diff_score > threshold:
                    timestamp = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
                    scene_changes.append(timestamp)

            prev_frame = frame

        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        return scene_changes

    def _calculate_frame_difference(self, frame1: np.ndarray, frame2: np.ndarray) -> floating[Any]:
        """
        Computes the mean absolute difference between two grayscale frames.
        Used as a heuristic for scene change detection.
        """
        gray1 = cv2.cvtColor(frame1, cv2.COLOR_RGB2GRAY)
        gray2 = cv2.cvtColor(frame2, cv2.COLOR_RGB2GRAY)
        diff = cv2.absdiff(gray1, gray2)
        return np.mean(diff)

    def _extract_frames(
        self,
        cap: cv2.VideoCapture,
        target_frames: int,
        scene_changes: List[float],
    ) -> List[Frame]:
        """
        Extract evenly spaced frames and mark samples near detected transitions.
        """
        return self._extract_indexed_frames(cap, target_frames, scene_changes=scene_changes)


class UniformFrameSelector(FrameSelector):
    """
    Uniform frame selection strategy that picks frames at regular time intervals.
    Ideal for videos where scene content is relatively consistent.
    """

    def select_frames(self, video_path: str, frame_options: FrameOptions) -> List[Frame]:
        """
        Selects a target number of frames distributed evenly across the video duration.
        """
        self.logger.debug("Starting uniform frame selection")
        cap, fps, duration, total_frames = self._validate_video(video_path)

        target_frames = frame_options.calculate_uniform_frame_count(duration)
        self.logger.debug(f"Target frames for uniform selection: {target_frames}")
        try:
            frames = self._extract_uniform_frames(cap, target_frames, fps)
        finally:
            cap.release()
        self.logger.debug(f"Uniform frame selection completed. Selected {len(frames)} frames")
        return frames

    def _extract_uniform_frames(
        self,
        cap: cv2.VideoCapture,
        target_frames: int,
        fps: float,
    ) -> List[Frame]:
        """
        Inner logic to jump to specific frame indices based on uniform spacing.
        """
        return self._extract_indexed_frames(cap, target_frames, log_indices=True)


class AllFrameSelector(FrameSelector):
    """
    Exhaustive frame selection strategy that extracts every single frame.
    Recommended only for very short video clips.
    """

    def select_frames(self, video_path: str, frame_options: FrameOptions) -> List[Frame]:
        """
        Extracts all frames sequentially from the video.
        """
        self.logger.debug("Starting all frame selection")
        cap, fps, duration, total_frames = self._validate_video(video_path)

        try:
            frames = self._extract_all_frames(cap, fps)
        finally:
            cap.release()
        self.logger.debug(f"All frame selection completed. Selected {len(frames)} frames")
        return frames

    def _extract_all_frames(self, cap: cv2.VideoCapture, fps: float) -> List[Frame]:
        """Sequential extraction loop for all frames."""
        frames = []
        frame_idx = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            timestamp = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            frames.append(
                Frame(
                    image=frame_rgb,
                    timestamp=timestamp,
                    scene_type=SceneType.STATIC,  # Or determine dynamically if needed
                )
            )

            frame_idx += 1
            if frame_idx % 100 == 0:
                self.logger.debug(f"Extracted {frame_idx} frames")

        return frames
