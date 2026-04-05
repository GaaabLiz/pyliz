from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2


def sample_video_frames(video_path: str | Path, max_frames: int = 5) -> list[Any]:
    """
    Samples evenly distributed RGB frames from a video for downstream processing.
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError(f"Cannot open video file: {video_path}")

    try:
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames <= 0:
            return []

        indices = _build_frame_indices(total_frames=total_frames, max_frames=max_frames)
        frames = []
        for frame_idx in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ok, frame = cap.read()
            if not ok:
                continue
            frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        return frames
    finally:
        cap.release()



def _build_frame_indices(*, total_frames: int, max_frames: int) -> list[int]:
    if total_frames <= max_frames:
        return list(range(total_frames))

    step = max(total_frames // max_frames, 1)
    indices = list(range(0, total_frames, step))[:max_frames]
    if (total_frames - 1) not in indices:
        indices[-1] = total_frames - 1
    return indices

