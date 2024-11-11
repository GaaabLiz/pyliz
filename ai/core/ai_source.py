from typing import List

from ai.core.ai_env import AiEnvType
from ai.core.ai_file_type import AiFileType, AiFile, AiHgFile
from util import unitutils


class AiSource:

    def __init__(
            self,
            env: AiEnvType,
            model_name: str,
            ai_files: List[AiFile] | None = None,
            hg_files: List[AiHgFile] | None = None,
            ai_dirs: List[str] | None = None,
    ):
        self.ai_files = ai_files
        self.model_name = model_name
        self.env = env
        self.hg_files = hg_files
        self.ai_dirs = ai_dirs

    def get_ggml_file(self) -> AiFile:
        for hg_file in self.ai_files:
            if hg_file.file_type == AiFileType.HG_GGML:
                return hg_file
        raise Exception("No ggml file found in the source.")

    def get_mmproj_file(self) -> AiFile:
        for hg_file in self.ai_files:
            if hg_file.file_type == AiFileType.HG_MMPROJ:
                return hg_file
        raise Exception("No mmproj file found in the source.")

    def get_main_ai_file(self) -> AiFile:
        if len(self.ai_files) == 1:
            return self.ai_files[0]
        raise Exception("More than one ai file found in the source.")

    def get_files_size_mb(self) -> float:
        total = 0.0
        for hg_file in self.ai_files:
            size_byte = hg_file.get_file_size_byte()
            size_mb = unitutils.convert_byte_to_mb(size_byte)
            total += size_mb
        return total

