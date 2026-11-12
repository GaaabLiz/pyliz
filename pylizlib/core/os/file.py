"""Compatibility exports for historical file helper imports.

New code should use ``filesystem.file_types``, ``filesystem.files`` and
``filesystem.json`` for file inspection and ``core.network.download`` for HTTP
downloads. This module retains the original public imports.
"""

from pylizlib.core.domain.operation import Operation
from pylizlib.core.domain.os import FileType
from pylizlib.core.network.download import download_file
from pylizlib.core.os.filesystem.file_types import (
    audio_extensions,
    get_file_type,
    image_extensions,
    is_audio_extension,
    is_audio_file,
    is_image_extension,
    is_image_file,
    is_image_or_video_file,
    is_media_file,
    is_media_sidecar_file,
    is_text_extension,
    is_text_file,
    is_video_extension,
    is_video_file,
    text_extensions,
    video_extensions,
)
from pylizlib.core.os.filesystem.files import get_file_c_date, is_file_dup_in_dir
from pylizlib.core.os.filesystem.json import write_json_to_file

__all__ = [
    "FileType",
    "Operation",
    "audio_extensions",
    "download_file",
    "get_file_c_date",
    "get_file_type",
    "image_extensions",
    "is_audio_extension",
    "is_audio_file",
    "is_file_dup_in_dir",
    "is_image_extension",
    "is_image_file",
    "is_image_or_video_file",
    "is_media_file",
    "is_media_sidecar_file",
    "is_text_extension",
    "is_text_file",
    "is_video_extension",
    "is_video_file",
    "text_extensions",
    "video_extensions",
    "write_json_to_file",
]
