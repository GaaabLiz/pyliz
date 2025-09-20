import json
import os
from typing import Optional, List

import cv2
import ffmpeg
from sd_parsers import ParserManager
from sd_parsers.data import PromptInfo

from pylizlib.core.domain.os import FileType
from pylizlib.core.log.pylizLogger import logger
from pylizlib.core.os.file import get_file_c_date, get_file_type, is_media_file
from pylizlib.media.domain.ai import AiPayloadMediaInfo


class LizMedia:

    def __init__(self, path: str):

        # file info
        self.path = path
        self.file_name = os.path.basename(self.path)
        self.extension = os.path.splitext(path)[1].lower()
        self.creation_time = get_file_c_date(self.path)
        self.creation_time_timestamp: float = self.creation_time.timestamp()
        self.year, self.month, self.day = self.creation_time.year, self.creation_time.month, self.creation_time.day
        self.size_byte = os.path.getsize(self.path)
        self.size_mb = self.size_byte / (1024 * 1024)

        # type of media
        if not is_media_file(self.path):
            raise ValueError(f"File {self.path} is not a media file.")
        self.type = get_file_type(self.path)
        self.is_image = self.type == FileType.IMAGE
        self.is_video = self.type == FileType.VIDEO
        self.is_audio = self.type == FileType.AUDIO

        # ai info
        self.ai_ocr_text: Optional[List[str]] = None
        self.ai_file_name: Optional[str] = None
        self.ai_description: Optional[str] = None
        self.ai_tags: Optional[List[str]] = None
        self.ai_scanned: bool = False
        self.ai_generated: bool = False
        self.ai_metadata: PromptInfo | None = None
        self.__check_for_ai_metadata()

        # video info
        if self.is_video:
            self.duration_sec: Optional[float] = self.get_video_duration_seconds()
            self.duration_min: Optional[float] = self.duration_sec / 60
            self.frame_rate: Optional[float] = self.get_video_frame_rate()
        else:
            self.duration_sec = None
            self.duration_min = None
            self.frame_rate = None

    def __check_for_ai_metadata(self):
        try:
            if self.is_image:
                parser_manager = ParserManager()
                prompt_info: PromptInfo | None = parser_manager.parse(self.path)
                if prompt_info is not None:
                    self.ai_metadata = prompt_info
                    self.ai_generated = True
        except Exception as e:
            logger.error(f"Error checking for AI metadata with sdParser: {str(e)}")


    def get_desc_plus_text(self):
        if self.ai_ocr_text is not None and len(self.ai_ocr_text) > 0:
            text_array = []
            for text in self.ai_ocr_text:
                text_array.append(text)
            return self.ai_description + " This media includes texts: " + " ".join(text_array)
        return self.ai_description

    def get_video_duration_seconds(self) -> float:
        try:
            probe = ffmpeg.probe(self.path)
            duration = float(probe['format']['duration'])
            return duration
        except Exception as e:
            logger.error(f"Error getting video duration: {str(e)}")
        return 0.0

    def get_video_frame_rate(self) -> float:
        """
        Restituisce il frame rate (FPS) del video.
        """
        try:
            video = cv2.VideoCapture(self.path)
            if not video.isOpened():
                logger.error("Errore: impossibile aprire il video.")
                return 0.0

            # Ottieni il frame rate
            fps = video.get(cv2.CAP_PROP_FPS)
            video.release()

            # Ritorna il valore di FPS
            return fps
        except Exception as e:
            logger.error(f"Errore nel calcolo del frame rate del video: {e}")
            return 0.0

    def to_dict_only_ai(self):
        return {
            "path": self.path,
            "file_name": self.file_name,
            "extension": self.extension,
            "creation_time_timestamp": self.creation_time_timestamp,
            "size_byte": self.size_byte,
            "size_mb": self.size_mb,
            "ai_ocr_text": self.ai_ocr_text,
            "ai_file_name": self.ai_file_name,
            "ai_description": self.ai_description,
            "ai_tags": self.ai_tags,
            "ai_scanned": self.ai_scanned,
        }

    def to_json_only_ai(self):
        return json.dumps(self.to_dict_only_ai(), indent=4)

    def apply_ai_info(self, ai_info: AiPayloadMediaInfo):
        self.ai_ocr_text = ai_info.text
        self.ai_file_name = ai_info.filename
        self.ai_description = ai_info.description
        self.ai_tags = ai_info.tags
        self.ai_scanned = True

