import os
from datetime import datetime
from typing import List

from util import osutils, fileutils
from util.datautils import convert_months_number_to_str


class LizImage:

    def __init__(self, image_path):
        self.ai_text: List[str] | None = None
        self.ai_file_name = None
        self.ai_description = None
        self.ai_tags = None
        self.ai_scanned = False
        self.path = image_path
        self.file_name = os.path.basename(self.path)
        self.extension = os.path.splitext(image_path)[1].lower()
        self.creation_time = fileutils.get_file_c_date(self.path)
        self.creation_time_timestamp: float = self.creation_time.timestamp()
        self.year, self.month, self.day = self.creation_time.year, self.creation_time.month, self.creation_time.day
        self.size_byte = os.path.getsize(self.path)
        self.size_mb = self.size_byte / (1024 * 1024)
        # self.output_path = None

    def __str__(self):
        return f"Image: {self.file_name} - {self.size_mb} MB - {self.year}/{self.month}/{self.day}"

    def __repr__(self):
        return f"Image: {self.file_name} - {self.size_mb} MB - {self.year}/{self.month}/{self.day}"

    def set_ai_tags(self, tags):
        self.ai_tags = tags

    def set_ai_description(self, description):
        self.ai_description = description

    def set_ai_filename(self, filename):
        self.ai_file_name = filename

    def set_ai_text(self, text):
        self.ai_text = text

    def set_ai_scanned(self, scanned):
        self.ai_scanned = scanned

    def get_desc_plus_text(self):
        if self.ai_text is not None and len(self.ai_text) > 0:
            return self.ai_description + " This image includes texts: " + self.ai_text
        return self.ai_description

