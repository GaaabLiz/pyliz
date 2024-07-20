from typing import List

from ai.model.hg_file import HgFile
from model.file_type import FileType


class AiSource:

    def __init__(
            self,
            ollama_name: str | None = None,
            local_name: str | None = None,
            url: str | None = None,
            hg_files: List[HgFile] | None = None,
    ):
        self.url = url
        self.hg_files = hg_files
        self.ollama_name = ollama_name
        self.local_name = local_name

    def get_ggml_file(self) -> HgFile:
        for hg_file in self.hg_files:
            if hg_file.file_type == FileType.HG_GGML:
                return hg_file
        raise Exception("No ggml file found in the source.")

    def get_mmproj_file(self) -> HgFile:
        for hg_file in self.hg_files:
            if hg_file.file_type == FileType.HG_MMPROJ:
                return hg_file
        raise Exception("No mmproj file found in the source.")