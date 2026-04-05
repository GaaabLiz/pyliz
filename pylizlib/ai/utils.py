from __future__ import annotations

import base64
import binascii
import mimetypes
import os
import tempfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Iterable

from PIL import Image


@dataclass(slots=True)
class ResolvedMediaSource:
    path: Path
    base64_content: str | None = None
    is_temporary: bool = False


def resolve_media_source(
    *,
    media_path: str | Path | None = None,
    base64_content: str | None = None,
    file_name: str | None = None,
) -> ResolvedMediaSource:
    if media_path is None and base64_content is None:
        raise ValueError("Either 'media_path' or 'base64_content' must be provided.")
    if media_path is not None and base64_content is not None:
        raise ValueError("Provide either 'media_path' or 'base64_content', not both.")

    if media_path is not None:
        path = Path(media_path).expanduser().resolve()
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Media file not found: {path}")
        return ResolvedMediaSource(path=path)

    payload, mime_type = _split_data_uri(base64_content or "")
    raw_bytes = _decode_base64(payload)
    suffix = _resolve_suffix(raw_bytes=raw_bytes, file_name=file_name, mime_type=mime_type)
    temp_path = _write_temp_file(raw_bytes, suffix=suffix)
    return ResolvedMediaSource(path=temp_path, base64_content=base64_content, is_temporary=True)


def sample_video_frames(video_path: str | Path, max_frames: int = 5) -> list:
    import cv2

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


def unique_preserving_order(values: Iterable[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        ordered.append(normalized)
        seen.add(normalized)
    return ordered


def _split_data_uri(value: str) -> tuple[str, str | None]:
    if value.startswith("data:") and "," in value:
        header, payload = value.split(",", 1)
        mime_type = header[5:].split(";", 1)[0] or None
        return payload, mime_type
    return value, None


def _decode_base64(value: str) -> bytes:
    try:
        return base64.b64decode(value, validate=True)
    except binascii.Error as exc:
        raise ValueError("Invalid base64 media payload.") from exc


def _resolve_suffix(*, raw_bytes: bytes, file_name: str | None, mime_type: str | None) -> str:
    file_suffix = Path(file_name).suffix.lower() if file_name else ""
    if file_suffix:
        return file_suffix

    mime_suffix = _mime_to_suffix(mime_type)
    if mime_suffix:
        return mime_suffix

    image_suffix = _detect_image_suffix(raw_bytes)
    if image_suffix:
        return image_suffix

    raise ValueError(
        "Unable to infer a file extension from base64 content. Provide 'file_name' or use a data URI base64 payload."
    )


def _mime_to_suffix(mime_type: str | None) -> str | None:
    if mime_type is None:
        return None

    guessed = mimetypes.guess_extension(mime_type)
    if guessed == ".jpe":
        return ".jpg"
    if guessed == ".qt":
        return ".mov"
    return guessed


def _detect_image_suffix(raw_bytes: bytes) -> str | None:
    try:
        with Image.open(BytesIO(raw_bytes)) as image:
            fmt = (image.format or "").lower()
    except Exception:
        return None

    return {
        "jpeg": ".jpg",
        "png": ".png",
        "webp": ".webp",
        "bmp": ".bmp",
        "gif": ".gif",
        "tiff": ".tiff",
    }.get(fmt)


def _write_temp_file(raw_bytes: bytes, *, suffix: str) -> Path:
    fd, temp_path = tempfile.mkstemp(prefix="pyliz_ai_", suffix=suffix)
    with os.fdopen(fd, "wb") as handle:
        handle.write(raw_bytes)
    return Path(temp_path)


def _build_frame_indices(*, total_frames: int, max_frames: int) -> list[int]:
    if total_frames <= max_frames:
        return list(range(total_frames))

    step = max(total_frames // max_frames, 1)
    indices = list(range(0, total_frames, step))[:max_frames]
    if (total_frames - 1) not in indices:
        indices[-1] = total_frames - 1
    return indices


