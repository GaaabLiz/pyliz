
import os

from ai.llm.controller.gemini import GeminiController
from ai.llm.controller import *
from ai.llm.controller.mistral import MistralController
from ai.llm.controller.whisper import WhisperController
from ai.llm.local.llamacpp import LlamaCpp
from ai.core.ai_setting import AiQuery
from ai.core.ai_source_type import AiSourceType
from ai.llm.local.whisper import Whisper
from model.operation import Operation
from util import datautils
from util.pylizdir import PylizDir, PylizDirFoldersTemplate


class AiRunner:

    def __init__(self, pyliz_dir: PylizDir):
        self.query = None
        self.pyliz_dir = pyliz_dir
        self.folder_ai = self.pyliz_dir.get_folder_path("ai")
        self.folder_logs = self.pyliz_dir.get_folder_path("logs")
        self.model_folder = self.pyliz_dir.get_folder_path("models")
        self.temp_folder = self.pyliz_dir.get_folder_template_path(PylizDirFoldersTemplate.TEMP)
        if not datautils.all_not_none(self.folder_ai, self.folder_logs, self.model_folder, self.temp_folder):
            raise ValueError("Some folders are not set in PylizDir")


    def __handle_mistral(self) -> Operation[str]:
        controller = MistralController(self.query.setting.api_key)
        return controller.run(self.query)

    def __handle_git_llama_cpp(self) -> Operation[str]:
        folder = os.path.join(self.folder_ai, "llama.cpp")
        logs = os.path.join(self.folder_logs, "llama.cpp")
        llama_cpp = LlamaCpp(folder, self.model_folder, logs)
        pass

    def __handle_gemini(self):
        controller = GeminiController(self.query.setting.api_key)
        return controller.run(self.query)

    def __handle_whisper(self):
        return WhisperController.run(self.query, self.model_folder, self.temp_folder)


    def run(self, query: AiQuery) -> Operation[str]:
        self.query = query
        if self.query.setting.source_type == AiSourceType.API_MISTRAL:
            return self.__handle_mistral()
        if self.query.setting.source_type == AiSourceType.LOCAL_LLAMACPP:
            return self.__handle_git_llama_cpp()
        if self.query.setting.source_type == AiSourceType.API_GEMINI:
            return self.__handle_gemini()
        if self.query.setting.source_type == AiSourceType.LOCAL_WHISPER:
            return self.__handle_whisper()
        raise NotImplementedError("Source type not implemented yet in AiRunner")