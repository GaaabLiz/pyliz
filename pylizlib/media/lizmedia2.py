import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PIL import Image, ExifTags
from sd_parsers import ParserManager
from sd_parsers.data import PromptInfo

from pylizlib.core.domain.os import FileType
from pylizlib.core.log.pylizLogger import logger
from pylizlib.core.os.file import get_file_type, is_media_file, get_file_c_date
from pylizlib.eaglecool.model.metadata import Metadata
from pylizlib.media.util.video import VideoUtils


# noinspection DuplicatedCode
@dataclass
class LizMedia:
    path: Path
    eagle_metadata_path: Path | None = None
    eagle_metadata: Metadata | None = None


    def __post_init__(self):
        if not is_media_file(self.path.__str__()):
            raise ValueError(f"File {self.path} is not a media file.")


    # ---- GENERAL FILE INFO

    @property
    def file_name(self) -> str:
        return self.path.name

    @property
    def extension(self) -> str:
        return self.path.suffix.lower()

    @property
    def creation_time(self) -> datetime:
        return get_file_c_date(self.path.__str__())

    @property
    def creation_time_timestamp(self) -> float:
        return self.creation_time.timestamp()

    @property
    def year(self) -> int:
        return self.creation_time.year

    @property
    def month(self) -> int:
        return self.creation_time.month

    @property
    def day(self) -> int:
        return self.creation_time.day

    @property
    def size_byte(self) -> int:
        return os.path.getsize(self.path.__str__())

    @property
    def size_mb(self) -> float:
        return self.size_byte / (1024 * 1024)

    @property
    def type(self) -> FileType:
        return get_file_type(self.path.__str__())

    @property
    def is_image(self) -> bool:
        return self.type == FileType.IMAGE

    @property
    def is_video(self) -> bool:
        return self.type == FileType.VIDEO

    @property
    def is_audio(self) -> bool:
        return self.type == FileType.AUDIO



    # ---- IMAGE FILE INFO

    @property
    def stable_diffusion_metadata(self) -> PromptInfo | None:
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
        if self.is_image:
            try:
                with Image.open(self.path) as img:
                    exif = img._getexif()
                    if exif:
                        for tag, value in exif.items():
                            decoded = ExifTags.TAGS.get(tag, tag)
                            if decoded == 'DateTimeOriginal':
                                return datetime.strptime(value, "%Y:%m:%d %H:%M:%S")
            except Exception as e:
                logger.error(f"Error reading EXIF data from {self.path}: {e}")

        return self.creation_time

    @property
    def has_exif_data(self) -> bool:
        if self.is_image:
            try:
                with Image.open(self.path) as img:
                    return img._getexif() is not None
            except Exception as e:
                logger.error(f"Error checking EXIF data for {self.path}: {e}")
        return False



    # ----  IMAGE/VIDEO INFO

    @property
    def ai_generated(self) -> bool:
        metadata = self.stable_diffusion_metadata
        return metadata is not None



    # ---- VIDEO FILE INFO

    @property
    def duration_sec(self) -> float | None:
        if not self.is_video:
            return None
        return VideoUtils.get_video_duration_seconds(self.path.__str__())

    @property
    def duration_min(self) -> float | None:
        if not self.is_video:
            return None
        duration = self.duration_sec
        if duration is not None:
            return duration / 60
        return None

    @property
    def frame_rate(self) -> float | None:
        if not self.is_video:
            return None
        return VideoUtils.get_video_frame_rate(self.path.__str__())




    # IMAGE UTILS

    def attach_eagle_metadata_path(self, eagle_metadata_path: Path):
        """
        Attaches Eagle metadata file path to the LizMedia instance.
        """
        self.eagle_metadata_path = eagle_metadata_path

    def attach_eagle_metadata(self, metadata: Metadata):
        """
        Attaches Eagle metadata to the LizMedia instance.
        """
        self.eagle_metadata = metadata

