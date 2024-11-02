
import os

from ai.llm.controller import GeminiController
from ai.llm.controller import MistralController
from ai.llm.local.llamacpp import LlamaCpp
from ai.core.ai_setting import AiQuery
from ai.core.ai_source_type import AiSourceType
from model.operation import Operation
from util.pylizdir import PylizDir


class AiRunner:

    def __init__(self, pyliz_dir: PylizDir):
        self.query = None
        self.pyliz_dir = pyliz_dir
        self.folder_ai = self.pyliz_dir.get_folder_path("ai")
        self.folder_logs = self.pyliz_dir.get_folder_path("logs")
        self.model_folder = self.pyliz_dir.get_folder_path("models")

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


    def run(self, query: AiQuery) -> Operation[str]:
        self.query = query
        if self.query.setting.source_type == AiSourceType.API_MISTRAL:
            return self.__handle_mistral()
        if self.query.setting.source_type == AiSourceType.LOCAL_LLAMACPP:
            return self.__handle_git_llama_cpp()
        if self.query.setting.source_type == AiSourceType.API_GEMINI:
            return self.__handle_gemini()
        raise NotImplementedError("Source type not implemented yet in AiRunner")