from enum import Enum

from model.file_type import FileType
from network import netutils


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

    def get_file_size_byte(self) -> int:
        return netutils.get_file_size_byte(self.url)

