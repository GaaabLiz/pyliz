import json
import os
from typing import Optional, List

from util import fileutils


class LizMedia:

    def __init__(self, path: str):

        # file info
        self.path = path
        self.file_name = os.path.basename(self.path)
        self.extension = os.path.splitext(path)[1].lower()
        self.creation_time = fileutils.get_file_c_date(self.path)
        self.creation_time_timestamp: float = self.creation_time.timestamp()
        self.year, self.month, self.day = self.creation_time.year, self.creation_time.month, self.creation_time.day
        self.size_byte = os.path.getsize(self.path)
        self.size_mb = self.size_byte / (1024 * 1024)

        # type of media
        self.is_image = fileutils.is_image_file(self.path)
        self.is_video = fileutils.is_video_file(self.path)

        # ai info
        self.ai_ocr_text: Optional[List[str]] = None
        self.ai_file_name: Optional[str] = None
        self.ai_description: Optional[str] = None
        self.ai_tags: Optional[List[str]] = None
        self.ai_scanned: bool = False

        # video info
        if self.is_video:
            self.duration: Optional[float] = self.get_video_duration()
            self.frame_rate: Optional[float] = self.get_video_frame_rate()
        else:
            self.duration = None
            self.frame_rate = None

    def get_desc_plus_text(self):
        if self.ai_ocr_text is not None and len(self.ai_ocr_text) > 0:
            return self.ai_description + " This media includes texts: " + self.ai
        return self.ai_description

    def get_video_duration(self) -> float:
        # Logica per ottenere la durata del video (da implementare)
        return 0.0

    def get_video_frame_rate(self) -> float:
        # Logica per ottenere il frame rate del video (da implementare)
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