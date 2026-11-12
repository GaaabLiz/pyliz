from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2


def sample_video_frames(video_path: str | Path, max_frames: int = 5) -> list[Any]:
    """
    Samples evenly distributed RGB frames from a video for downstream processing.
    Calculates uniform intervals to ensure the selection covers the full duration.

    Args:
        video_path: Path to the source video file.
        max_frames: Max number of frames to extract. Actual count might be lower for short videos.

    Returns:
        List of RGB frames as numpy arrays.

    Raises:
        ValueError: If the video cannot be opened.
    """
    frames, _ = sample_video_frames_with_count(video_path, max_frames=max_frames)
    return frames


def sample_video_frames_with_count(video_path: str | Path, max_frames: int = 5) -> tuple[list[Any], int]:
    """Return sampled frames and the number of frame indices attempted."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError(f"Cannot open video file: {video_path}")

    try:
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames <= 0:
            return [], 0

        indices = _build_frame_indices(total_frames=total_frames, max_frames=max_frames)
        frames = []
        for frame_idx in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ok, frame = cap.read()
            if not ok:
                continue
            frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        return frames, len(indices)
    finally:
        cap.release()


def _build_frame_indices(*, total_frames: int, max_frames: int) -> list[int]:
    """
    Calculates frame indices that are evenly spaced across the video.
    Ensures the first and last frames are included if possible.
    """
    if max_frames <= 0:
        raise ValueError("max_frames must be greater than zero")
    if total_frames <= 0:
        return []
    if total_frames <= max_frames:
        return list(range(total_frames))
    if max_frames == 1:
        return [0]

    last_index = total_frames - 1
    denominator = max_frames - 1
    return [int(index * last_index / denominator + 0.5) for index in range(max_frames)]
