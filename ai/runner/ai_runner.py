
import os
from tabnanny import check

from loguru import logger

from ai.llm.controller.gemini import GeminiController
from ai.llm.controller import *
from ai.llm.controller.mistral import MistralController
from ai.llm.controller.whisper import WhisperController
from ai.llm.local.llamacpp import LlamaCpp
from ai.core.ai_setting import AiQuery
from ai.core.ai_source_type import AiSourceType
from ai.llm.local.whisper import Whisper
from ai.util.ai_chkr import AiRunChecker
from model.operation import Operation
from util import datautils
from util.pylizdir import PylizDir, PylizDirFoldersTemplate


class AiRunner:

    def __init__(self, pyliz_dir: PylizDir):
        self.query = None
        self.pyliz_dir = pyliz_dir
        self.app_folder_ai = self.pyliz_dir.get_folder_path("ai")
        self.app_folder_logs = self.pyliz_dir.get_folder_path("logs")
        self.app_model_folder = self.pyliz_dir.get_folder_path("models")
        self.app_temp_folder = self.pyliz_dir.get_folder_template_path(PylizDirFoldersTemplate.TEMP)
        if not datautils.all_not_none(self.app_folder_ai, self.app_folder_logs, self.app_model_folder, self.app_temp_folder):
            raise ValueError("Some folders are not set in PylizDir")


    def __handle_mistral(self) -> Operation[str]:
        controller = MistralController(self.query.setting.api_key)
        return controller.run(self.query)

    def __handle_git_llama_cpp(self) -> Operation[str]:
        folder = os.path.join(self.app_folder_ai, "llama.cpp")
        logs = os.path.join(self.app_folder_logs, "llama.cpp")
        llama_cpp = LlamaCpp(folder, self.app_model_folder, logs)
        pass

    def __handle_gemini(self):
        controller = GeminiController(self.query.setting.api_key)
        return controller.run(self.query)

    def __handle_whisper(self):
        controller = WhisperController(self.app_model_folder, self.app_temp_folder)
        return controller.run(self.query)


    def run(self, query: AiQuery) -> Operation[str]:
        self.query = query
        try:
            checker = AiRunChecker(self.query, self.app_model_folder, self.app_folder_ai)
            checker.check_params()
            checker.check_source()
        except Exception as e:
            logger.error(f"Error while checking requirements: {e}. Ai query aborted.")
            return Operation(status=False, error=str(e))
        logger.info("Requirements checked. Proceeding with AI query...")
        if self.query.setting.source_type == AiSourceType.API_MISTRAL:
            return self.__handle_mistral()
        if self.query.setting.source_type == AiSourceType.LOCAL_LLAMACPP:
            return self.__handle_git_llama_cpp()
        if self.query.setting.source_type == AiSourceType.API_GEMINI:
            return self.__handle_gemini()
        if self.query.setting.source_type == AiSourceType.LOCAL_WHISPER:
            return self.__handle_whisper()
        raise NotImplementedError("Source type not implemented yet in AiRunner")