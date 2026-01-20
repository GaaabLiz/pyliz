import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Optional

import exifread
from PIL import Image
from sd_parsers import ParserManager
from sd_parsers.data import PromptInfo

from pylizlib.core.domain.os import FileType
from pylizlib.core.log.pylizLogger import logger
from pylizlib.core.os.file import get_file_type, is_media_file, get_file_c_date
from pylizlib.eaglecool.model.metadata import Metadata
from pylizlib.media.util.video import VideoUtils

# Suppress exifread logging
logging.getLogger('exifread').setLevel(logging.CRITICAL)


class MediaStatus(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


@dataclass
class LizMediaSearchResult:
    status: MediaStatus
    path: Path
    media: Optional['LizMedia'] = None
    reason: str = ""
    sidecar_files: List[Path] = field(default_factory=list)

    def has_lizmedia(self) -> bool:
        return self.media is not None

    def has_sidecars(self) -> bool:
        return len(self.sidecar_files) > 0


@dataclass
class MediaListResult:
    """
    Represents a collection of media files, distinguishing between those successfully found
    and those that were rejected during a search or process.

    Attributes:
        accepted (List[LizMediaSearchResult]): Successfully identified and processed media files.
        rejected (List[LizMediaSearchResult]): Media files that were identified but rejected for various reasons.
        errored (List[LizMediaSearchResult]): Media files that encountered errors during processing.
    """
    accepted: List[LizMediaSearchResult] = field(default_factory=list)
    rejected: List[LizMediaSearchResult] = field(default_factory=list)
    errored: List[LizMediaSearchResult] = field(default_factory=list)

    @property
    def total_count(self) -> int:
        """
        Returns the total number of media files processed (found + rejected + errored).
        """
        return len(self.accepted) + len(self.rejected) + len(self.errored)


# noinspection DuplicatedCode
@dataclass
class LizMedia:
    """
    Represents a media file (Image, Video, Audio) and provides access to its metadata and properties.

    This class serves as a wrapper around a file path, offering utility properties to access
    common file attributes (size, dates), media-specific data (EXIF, video duration), and
    integration with other tools like Eagle (metadata).

    Attributes:
        path (Path): The file system path to the media file.
        eagle_metadata_path (Path | None): Optional path to an associated Eagle metadata file.
        eagle_metadata (Metadata | None): Optional loaded Eagle metadata object.
    """
    path: Path
    eagle_metadata_path: Path | None = None
    eagle_metadata: Metadata | None = None

    def __post_init__(self):
        """
        Validates the media file after initialization.

        Checks if the provided path corresponds to a recognized media file type.

        Raises:
            ValueError: If the file at `self.path` is not identified as a valid media file.
        """
        if not is_media_file(self.path.__str__()):
            raise ValueError(f"File {self.path} is not a media file.")

    # ---- GENERAL FILE INFO

    @property
    def file_name(self) -> str:
        """
        Gets the name of the file including the extension.

        Returns:
            str: The filename (e.g., "image.png").
        """
        return self.path.name

    @property
    def extension(self) -> str:
        """
        Gets the file extension in lowercase.

        Returns:
            str: The file extension (e.g., ".jpg").
        """
        return self.path.suffix.lower()

    @property
    def creation_time(self) -> datetime:
        """
        Gets the creation date and time of the file.

        Uses the file system's creation time metadata.

        Returns:
            datetime: The creation timestamp as a datetime object.
        """
        return get_file_c_date(self.path.__str__())

    @property
    def creation_time_timestamp(self) -> float:
        """
        Gets the creation time as a POSIX timestamp.

        Returns:
            float: The creation time in seconds since the epoch.
        """
        return self.creation_time.timestamp()

    @property
    def year(self) -> int:
        """
        Gets the year component of the file's creation date.

        Returns:
            int: The year (e.g., 2023).
        """
        return self.creation_time.year

    @property
    def month(self) -> int:
        """
        Gets the month component of the file's creation date.

        Returns:
            int: The month (1-12).
        """
        return self.creation_time.month

    @property
    def day(self) -> int:
        """
        Gets the day component of the file's creation date.

        Returns:
            int: The day of the month (1-31).
        """
        return self.creation_time.day

    @property
    def size_byte(self) -> int:
        """
        Gets the file size in bytes.

        Returns:
            int: The size of the file in bytes.
        """
        return os.path.getsize(self.path.__str__())

    @property
    def size_mb(self) -> float:
        """
        Gets the file size in megabytes.

        Returns:
            float: The size of the file in MB.
        """
        return self.size_byte / (1024 * 1024)

    @property
    def type(self) -> FileType:
        """
        Determines the type of the media file (Image, Video, etc.).

        Returns:
            FileType: An enum representing the file type.
        """
        return get_file_type(self.path.__str__())

    @property
    def is_image(self) -> bool:
        """
        Checks if the file is an image.

        Returns:
            bool: True if the file is an image, False otherwise.
        """
        return self.type == FileType.IMAGE

    @property
    def is_video(self) -> bool:
        """
        Checks if the file is a video.

        Returns:
            bool: True if the file is a video, False otherwise.
        """
        return self.type == FileType.VIDEO

    @property
    def is_audio(self) -> bool:
        """
        Checks if the file is an audio file.

        Returns:
            bool: True if the file is audio, False otherwise.
        """
        return self.type == FileType.AUDIO

    # ---- IMAGE FILE INFO

    @property
    def stable_diffusion_metadata(self) -> PromptInfo | None:
        """
        Attempts to retrieve Stable Diffusion generation metadata from the image.

        Uses `sd_parsers` to extract prompt information from supported image formats.
        Logs an error if parsing fails.

        Returns:
            PromptInfo | None: The parsed prompt information if available, otherwise None.
        """
        if not self.is_image:
            return None
        try:
            if self.is_image:
                parser_manager = ParserManager()
                prompt_info: PromptInfo | None = parser_manager.parse(self.path)
                if prompt_info is not None:
                    return prompt_info
        except Exception as e:
            logger.error(f"Error checking for AI metadata with sdParser: {str(e)}")

    @property
    def creation_date_from_exif_or_file(self) -> datetime:
        """
        Retrieves the creation date from EXIF data (DateTimeOriginal) if available.
        Falls back to the file system creation time if EXIF data is missing or unreadable.
        Uses 'exifread' library for robust parsing.

        Returns:
            datetime: The determined creation date.
        """
        if self.is_image:
            try:
                with open(self.path, 'rb') as f:
                    tags = exifread.process_file(f, details=False)
                    # Try common creation date tags
                    for tag_key in ['EXIF DateTimeOriginal', 'Image DateTime', 'EXIF DateTimeDigitized']:
                        if tag_key in tags:
                            try:
                                return datetime.strptime(str(tags[tag_key]), "%Y:%m:%d %H:%M:%S")
                            except ValueError:
                                continue
            except Exception as e:
                # logger.error(f"Error reading EXIF data from {self.path}: {e}")
                pass

        return self.creation_time

    @property
    def has_exif_data(self) -> bool:
        """
        Checks if the image file contains any EXIF metadata.

        Returns:
            bool: True if EXIF data is present, False otherwise (or if not an image).
        """
        if self.is_image:
            try:
                with open(self.path, 'rb') as f:
                    tags = exifread.process_file(f, details=False)
                    return bool(tags)
            except Exception as e:
                # logger.error(f"Error checking EXIF data for {self.path}: {e}")
                pass
        return False

    # ----  IMAGE/VIDEO INFO

    @property
    def ai_generated(self) -> bool:
        """
        Determines if the media file is likely AI-generated.

        Currently checks for the presence of Stable Diffusion metadata.

        Returns:
            bool: True if AI generation metadata is found, False otherwise.
        """
        metadata = self.stable_diffusion_metadata
        return metadata is not None

    # ---- VIDEO FILE INFO

    @property
    def duration_sec(self) -> float | None:
        """
        Gets the duration of the video in seconds.

        Returns:
            float | None: The duration in seconds, or None if not a video or duration cannot be determined.
        """
        if not self.is_video:
            return None
        return VideoUtils.get_video_duration_seconds(self.path.__str__())

    @property
    def duration_min(self) -> float | None:
        """
        Gets the duration of the video in minutes.

        Returns:
            float | None: The duration in minutes, or None if not a video.
        """
        if not self.is_video:
            return None
        duration = self.duration_sec
        if duration is not None:
            return duration / 60
        return None

    @property
    def frame_rate(self) -> float | None:
        """
        Gets the frame rate (FPS) of the video.

        Returns:
            float | None: The frame rate, or None if not a video or cannot be determined.
        """
        if not self.is_video:
            return None
        return VideoUtils.get_video_frame_rate(self.path.__str__())

    # IMAGE UTILS

    def attach_eagle_metadata_path(self, eagle_metadata_path: Path):
        """
        Attaches the path of an associated Eagle metadata file to this instance.

        Args:
            eagle_metadata_path (Path): The path to the metadata file.
        """
        self.eagle_metadata_path = eagle_metadata_path

    def attach_eagle_metadata(self, metadata: Metadata):
        """
        Attaches a loaded Eagle metadata object to this instance.

        Args:
            metadata (Metadata): The metadata object to attach.
        """
        self.eagle_metadata = metadata