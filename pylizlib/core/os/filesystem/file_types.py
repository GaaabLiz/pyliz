"""File extension and media-type classification helpers."""

import os

from pylizlib.core.domain.os import FileType

image_extensions = [
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".tiff",
    ".svg",
    ".heic",
    ".heif",
    ".webp",
    ".ico",
    ".dng",
]
video_extensions = [".mp4", ".avi", ".mov", ".mkv", ".flv", ".wmv", ".webm", ".3gp"]
audio_extensions = [".mp3", ".wav", ".ogg", ".flac", ".wma", ".aac", ".m4a"]
text_extensions = [".txt", ".doc", ".docx", ".pdf", ".odt", ".rtf", ".tex"]


def is_image_extension(extension: str) -> bool:
    """Return whether an extension identifies an image format.

    Args:
        extension (str): File extension, with or without an initial dot.

    Returns:
        bool: Whether the extension is listed as an image format.
    """
    return extension.lower() in image_extensions


def is_video_extension(extension: str) -> bool:
    """Return whether an extension identifies a video format.

    Args:
        extension (str): File extension, with or without an initial dot.

    Returns:
        bool: Whether the extension is listed as a video format.
    """
    return extension.lower() in video_extensions


def is_audio_extension(extension: str) -> bool:
    """Return whether an extension identifies an audio format.

    Args:
        extension (str): File extension, with or without an initial dot.

    Returns:
        bool: Whether the extension is listed as an audio format.
    """
    return extension.lower() in audio_extensions


def is_text_extension(extension: str) -> bool:
    """Return whether an extension identifies a supported text or document format.

    Args:
        extension (str): File extension, with or without an initial dot.

    Returns:
        bool: Whether the extension is listed as a text or document format.
    """
    return extension.lower() in text_extensions


def is_image_file(path: str) -> bool:
    """Return whether a path's extension identifies an image format.

    Args:
        path (str): File path or name to inspect.

    Returns:
        bool: Whether the file extension is listed as an image format.
    """
    return is_image_extension(os.path.splitext(path)[1])


def is_video_file(path: str) -> bool:
    """Return whether a path's extension identifies a video format.

    Args:
        path (str): File path or name to inspect.

    Returns:
        bool: Whether the file extension is listed as a video format.
    """
    return is_video_extension(os.path.splitext(path)[1])


def is_audio_file(path: str) -> bool:
    """Return whether a path's extension identifies an audio format.

    Args:
        path (str): File path or name to inspect.

    Returns:
        bool: Whether the file extension is listed as an audio format.
    """
    return is_audio_extension(os.path.splitext(path)[1])


def is_text_file(path: str) -> bool:
    """Return whether a path's extension identifies a text or document format.

    Args:
        path (str): File path or name to inspect.

    Returns:
        bool: Whether the file extension is listed as a text or document format.
    """
    return is_text_extension(os.path.splitext(path)[1])


def is_image_or_video_file(path: str) -> bool:
    """Return whether a path is classified as an image or video.

    Args:
        path (str): File path or name to inspect.

    Returns:
        bool: Whether the path has a supported image or video extension.
    """
    return is_image_file(path) or is_video_file(path)


def is_media_file(path: str) -> bool:
    """Return whether a path is classified as image, video, or audio media.

    Args:
        path (str): File path or name to inspect.

    Returns:
        bool: Whether the path has a supported media extension.
    """
    return is_image_file(path) or is_video_file(path) or is_audio_file(path)


def is_media_sidecar_file(path: str) -> bool:
    """Return whether a path has a supported media-sidecar extension.

    Args:
        path (str): File path or name to inspect.

    Returns:
        bool: Whether the extension is XMP, XML, or AAE.
    """
    sidecar_extensions = [".xmp", ".xml", ".aae"]
    return os.path.splitext(path)[1].lower() in sidecar_extensions


def get_file_type(path: str) -> FileType:
    """Classify a supported file path by its extension.

    Args:
        path (str): File path or name to inspect.

    Returns:
        FileType: Supported image, video, audio, text, or sidecar type.

    Raises:
        ValueError: The extension is not supported by this classifier.
    """
    if is_image_file(path):
        return FileType.IMAGE
    elif is_video_file(path):
        return FileType.VIDEO
    elif is_audio_file(path):
        return FileType.AUDIO
    elif is_text_file(path):
        return FileType.TEXT
    elif is_media_sidecar_file(path):
        return FileType.MEDIA_SIDECAR
    else:
        raise ValueError("Unsupported file type")
