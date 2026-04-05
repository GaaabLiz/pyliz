from __future__ import annotations

import base64
import binascii
import mimetypes
import os
import tempfile
from io import BytesIO
from pathlib import Path

from PIL import Image

from pylizlib.media.domain.source import ResolvedMediaSource


def resolve_media_source(
    *,
    media_path: str | Path | None = None,
    base64_content: str | None = None,
    file_name: str | None = None,
) -> ResolvedMediaSource:
    """
    Resolves various media input formats into a single filesystem path for processing.
    Handles local paths, raw Base64, and Data URIs. If Base64 is provided,
    it creates a temporary file.

    Args:
        media_path: Optional path to a local media file.
        base64_content: Optional Base64 string (can be a Data URI).
        file_name: Recommended for Base64 inputs to help infer the file extension.

    Returns:
        A ResolvedMediaSource object containing the resolved Path and metadata.

    Raises:
        ValueError: If both or neither input sources are provided, or if Base64 is invalid.
        FileNotFoundError: If the provided media_path does not exist.
    """
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


def _split_data_uri(value: str) -> tuple[str, str | None]:
    """
    Splits a Data URI (e.g. 'data:image/png;base64,XXXX') into its
    raw Base64 payload and MIME type.
    """
    if value.startswith("data:") and "," in value:
        header, payload = value.split(",", 1)
        mime_type = header[5:].split(";", 1)[0] or None
        return payload, mime_type
    return value, None


def _decode_base64(value: str) -> bytes:
    """Decodes a Base64 string into raw bytes with validation."""
    try:
        return base64.b64decode(value, validate=True)
    except binascii.Error as exc:
        raise ValueError("Invalid base64 media payload.") from exc


def _resolve_suffix(*, raw_bytes: bytes, file_name: str | None, mime_type: str | None) -> str:
    """
    Heuristically determines the file extension for a media blob.
    Checks provided file_name first, then MIME type, and finally
    inspects image headers.
    """
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
    """Maps a MIME type to a normalized file extension."""
    if mime_type is None:
        return None

    guessed = mimetypes.guess_extension(mime_type)
    if guessed == ".jpe":
        return ".jpg"
    if guessed == ".qt":
        return ".mov"
    return guessed


def _detect_image_suffix(raw_bytes: bytes) -> str | None:
    """Uses PIL to detect the image format from raw bytes."""
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
    """Writes raw bytes to a secure temporary file on disk."""
    fd, temp_path = tempfile.mkstemp(prefix="pyliz_media_", suffix=suffix)
    with os.fdopen(fd, "wb") as handle:
        handle.write(raw_bytes)
    return Path(temp_path)


