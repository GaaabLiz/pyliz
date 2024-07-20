from enum import Enum

from model.file_type import FileType


class HgFile:
    def __init__(
            self,
            file_name: str,
            url: str,
            file_type: FileType
    ):
        self.file_name = file_name
        self.url = url
        self.file_type = file_type



