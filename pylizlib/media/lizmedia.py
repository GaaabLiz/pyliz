import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from itertools import count
from pathlib import Path
from typing import List, Optional, Any, TYPE_CHECKING

import exifread
from sd_parsers import ParserManager
from sd_parsers.data import PromptInfo

from pylizlib.core.domain.os import FileType
from pylizlib.core.log.pylizLogger import logger
from pylizlib.core.os.file import get_file_type, is_media_file, get_file_c_date
from pylizlib.media.util.metadata import MetadataHandler
from pylizlib.media.util.video import VideoUtils

if TYPE_CHECKING:
    from pylizlib.media.domain.ai import AiPayloadMediaInfo

# Suppress exifread logging
logging.getLogger('exifread').setLevel(logging.CRITICAL)


class MediaStatus(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"

# Global counter for LizMediaSearchResult index
_search_result_counter = count(1)

@dataclass
class LizMediaSearchResult:
    status: MediaStatus
    path: Path
    media: Optional['LizMedia'] = None
    reason: str = ""
    index: int = field(default_factory=lambda: next(_search_result_counter), init=False)

    def has_lizmedia(self) -> bool:
        return self.media is not None

    def has_sidecars(self) -> bool:
        if self.media:
            return len(self.media.attached_sidecar_files) > 0
        return False


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
    eagle_metadata: Any | None = None
    attached_sidecar_files: List[Path] = field(default_factory=list)
    base64_content: Optional[str] = None
    ai_ocr_text: Optional[List[str]] = None
    ai_file_name: Optional[str] = None
    ai_description: Optional[str] = None
    ai_tags: Optional[List[str]] = None
    ai_scanned: bool = False
    ai_nsfw: Optional[bool] = None
    ai_has_ocr_text: Optional[bool] = None

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
        Gets the file size in megabytes (decimal, matching macOS Finder).

        Returns:
            float: The size of the file in MB.
        """
        return self.size_byte / 1000000

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
    def creation_date_from_exif_or_file_or_sidecar(self) -> datetime:
        """
        Retrieves the creation date from EXIF data (DateTimeOriginal) if available.
        Falls back to Video metadata (QuickTime/MP4 tags) if it's a video.
        Falls back to XMP sidecar (<photoshop:DateCreated>) if present.
        Falls back to the file system creation time if both are missing or unreadable.
        Uses 'exifread' library for robust parsing and 'ffmpeg' for videos.

        Returns:
            datetime: The determined creation date.
        """
        # 1. Try EXIF (Standard Python library)
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
                pass
            
            # 1b. Robust Exiftool Fallback for Images
            handler = MetadataHandler(self.path)
            exiftool_date = handler.get_image_creation_date()
            if exiftool_date:
                return exiftool_date

        # 2. Try Video Metadata (using ffmpeg/ffprobe)
        if self.is_video:
            ts = VideoUtils.get_video_creation_date(self.path.__str__())
            if ts:
                return datetime.fromtimestamp(ts)

        # 3. Try XMP Sidecar
        xmp_date = self._get_creation_date_from_xmp()
        if xmp_date:
            return xmp_date

        # 4. Fallback to File Creation Time
        return self.creation_time

    def _get_creation_date_from_xmp(self) -> Optional[datetime]:
        """
        Attempts to extract the creation date from an attached XMP sidecar file.
        Looks for the <photoshop:DateCreated> tag.
        """
        xmp_path = self.get_xmp_sidecar()
        if not xmp_path or not xmp_path.exists():
            return None

        try:
            import re
            with open(xmp_path, 'r', encoding='utf-8') as f:
                content = f.read()
                # Simple regex search for photoshop:DateCreated
                # Format is typically ISO 8601: YYYY-MM-DDThh:mm:ss
                match = re.search(r'photoshop:DateCreated>([^<]+)<', content)
                if not match:
                    # Try attribute style
                    match = re.search(r'photoshop:DateCreated="([^"]+)"', content)
                
                if match:
                    date_str = match.group(1)
                    # Handle potential timezone offsets or variations
                    # Try basic ISO parsing
                    try:
                        dt = datetime.fromisoformat(date_str)
                        return dt.replace(tzinfo=None)
                    except ValueError:
                        # Try manual parsing if fromisoformat fails (e.g. for some XMP variants)
                        # This is a basic fallback, might need adjustment for specific formats
                        pass
        except Exception as e:
            logger.warning(f"Error reading XMP date from {xmp_path}: {e}")
        
        return None

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

    def get_desc_plus_text(self) -> Optional[str]:
        """
        Returns the AI description enriched with OCR text, when available.

        Returns:
            Optional[str]: The combined description, or the plain description if no OCR text exists.
        """
        if self.ai_description is None:
            return None
        if self.ai_ocr_text:
            return self.ai_description + " This media includes texts: " + " ".join(self.ai_ocr_text)
        return self.ai_description

    def to_dict_only_ai(self) -> dict[str, Any]:
        """
        Serializes only AI-related fields for this media.

        Returns:
            dict[str, Any]: A dictionary containing AI scan metadata.
        """
        return {
            "path": self.path.__str__(),
            "file_name": self.file_name,
            "extension": self.extension,
            "creation_time_timestamp": self.creation_time_timestamp,
            "size_byte": self.size_byte,
            "size_mb": self.size_mb,
            "ai_ocr_text": self.ai_ocr_text,
            "ai_has_ocr_text": self.ai_has_ocr_text,
            "ai_file_name": self.ai_file_name,
            "ai_description": self.ai_description,
            "ai_tags": self.ai_tags,
            "ai_scanned": self.ai_scanned,
            "ai_nsfw": self.ai_nsfw,
        }

    def to_json_only_ai(self) -> str:
        """
        Serializes AI-related fields as JSON.

        Returns:
            str: A pretty-printed JSON representation of AI fields.
        """
        return json.dumps(self.to_dict_only_ai(), indent=4)

    def apply_ai_info(self, ai_info: 'AiPayloadMediaInfo'):
        """
        Applies AI payload information to this media instance.

        Args:
            ai_info: The AI payload to merge into the current media object.
        """
        self.ai_ocr_text = ai_info.text
        self.ai_has_ocr_text = bool(ai_info.text)
        self.ai_file_name = ai_info.filename
        self.ai_description = ai_info.description
        self.ai_tags = ai_info.tags
        self.ai_scanned = True
        self.ai_nsfw = getattr(ai_info, "nsfw", None)

    def apply_ai_scan_result(
            self,
            *,
            tags: Optional[List[str]] = None,
            nsfw: Optional[bool] = None,
            ocr_text: Optional[List[str]] = None,
            has_ocr_text: Optional[bool] = None,
            description: Optional[str] = None,
            file_name: Optional[str] = None,
    ):
        """
        Applies normalized AI scan results to this media instance.

        Args:
            tags: Predicted tags generated by AI classifiers.
            nsfw: Whether the media contains NSFW content.
            ocr_text: OCR strings extracted from the media.
            has_ocr_text: Whether any OCR text was detected.
            description: Optional AI-generated description.
            file_name: Optional original filename associated with the AI payload.
        """
        if tags is not None:
            self.ai_tags = tags
        if nsfw is not None:
            self.ai_nsfw = nsfw
        if ocr_text is not None:
            self.ai_ocr_text = ocr_text
        if has_ocr_text is not None:
            self.ai_has_ocr_text = has_ocr_text
        elif ocr_text is not None:
            self.ai_has_ocr_text = bool(ocr_text)
        if description is not None:
            self.ai_description = description
        if file_name is not None:
            self.ai_file_name = file_name
        elif self.ai_file_name is None:
            self.ai_file_name = self.file_name

        self.ai_scanned = any(
            value is not None
            for value in [self.ai_tags, self.ai_nsfw, self.ai_ocr_text, self.ai_has_ocr_text, self.ai_description]
        )

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

    def attach_eagle_metadata(self, metadata: Any):
        """
        Attaches a loaded Eagle metadata object to this instance.

        Args:
            metadata (Metadata): The metadata object to attach.
        """
        self.eagle_metadata = metadata

    def attach_sidecar_file(self, sidecar_path: Path):
        """
        :param sidecar_path:   Path to sidecar file to attach
        :return:
        """
        self.attached_sidecar_files.append(sidecar_path)

    def detach_sidecar_file(self, sidecar_path: Path):
        """
        :param sidecar_path:   Path to sidecar file to detach
        :return:
        """
        if sidecar_path in self.attached_sidecar_files:
            self.attached_sidecar_files.remove(sidecar_path)

    def clear_sidecar_files(self):
        """
        Clears all attached sidecar files
        :return:
        """
        self.attached_sidecar_files.clear()

    def has_xmp_sidecar(self) -> bool:
        """
        Checks if there is an attached XMP sidecar file
        :return: True if an XMP sidecar file is attached, False otherwise
        """
        for sidecar in self.attached_sidecar_files:
            if sidecar.suffix.lower() == '.xmp':
                return True
        return False

    def has_aae_sidecar(self) -> bool:
        """
        Checks if there is an attached AAE sidecar file
        :return: True if an AAE sidecar file is attached, False otherwise
        """
        for sidecar in self.attached_sidecar_files:
            if sidecar.suffix.lower() == '.aae':
                return True
        return False

    def get_xmp_sidecar(self) -> Optional[Path]:
        """
        Retrieves the attached XMP sidecar file if it exists
        :return: Path to the XMP sidecar file, or None if not found
        """
        for sidecar in self.attached_sidecar_files:
            if sidecar.suffix.lower() == '.xmp':
                return sidecar
        return None