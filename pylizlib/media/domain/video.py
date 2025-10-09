from dataclasses import dataclass
from enum import Enum
from typing import List

import numpy as np

from pylizlib.core.log.pylizLogger import logger


class SceneType(Enum):
    STATIC = "static"
    ACTION = "action"
    TRANSITION = "transition"


@dataclass
class Frame:
    image: np.ndarray
    timestamp: float
    scene_type: SceneType
    difference_score: float = 0.0


class FrameOptions:

    def __init__(self, frames_per_minute: float = 4.0, min_frames: int = 2, max_frames: int = 64):
        self.frames_per_minute = frames_per_minute
        self.min_frames = min_frames
        self.max_frames = max_frames

    def calculate_dynamic_frame_count(self, video_duration: float, scene_changes: List[float]) -> int:
        """Calculate optimal number of frames to analyze"""
        base_frames = int(video_duration / 60 * self.frames_per_minute)
        scene_density = len(scene_changes) / video_duration if video_duration > 0 else 0
        scene_multiplier = min(2.0, max(0.5, scene_density * 30))
        optimal_frames = int(base_frames * scene_multiplier)
        return min(self.max_frames, max(self.min_frames, optimal_frames))

    def calculate_uniform_frame_count(self, video_duration: float) -> int:
        """Calculate the number of frames to select uniformly based on video duration."""
        base_frames = int((video_duration / 60) * self.frames_per_minute)
        optimal_frames = min(self.max_frames, max(self.min_frames, base_frames))
        logger.trace(
            f"Calculated uniform frame count: {optimal_frames} (Base: {base_frames}, Min: {self.min_frames}, Max: {self.max_frames})")
        return optimal_frames
