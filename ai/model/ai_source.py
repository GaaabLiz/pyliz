from typing import List

from ai.model.hg_file import HgFile


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
