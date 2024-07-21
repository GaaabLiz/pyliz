import base64
import os

from ai.core.ai_setting import AiSettings
from ai.llm.local.llamacpp import LlamaCpp
from ai.llm.remote.service.ollamaliz import Ollamaliz
from model.operation import Operation
from util.pylizdir import PylizDir


class LlavaController:

    def __init__(self, settings: AiSettings):
        self.settings = settings

    def run_from_ollama(self, image_path: str) -> Operation[str]:
        ollama = Ollamaliz(self.settings.remote_url)
        model_name = self.settings.source.ollama_name
        with open(image_path, "rb") as image_file:
            image_base_64 = base64.b64encode(image_file.read()).decode('utf-8')
        llava_result = ollama.llava_query(self.settings.prompt.value, image_base_64, model_name)
        if not llava_result.is_op_ok():
            return Operation(status=False, error=llava_result.error)
        return Operation(status=True, payload=llava_result.payload.response)

    def run_from_local_llamacpp(self, image_path: str) -> Operation[str]:
        PylizDir.create()
        path_install: str = os.path.join(PylizDir.get_ai_folder(), "llama.cpp")
        path_models: str = PylizDir.get_models_folder()
        path_logs: str = os.path.join(PylizDir.get_logs_path(), "llama.cpp")
        obj = LlamaCpp(path_install, path_models, path_logs)
        obj.install_llava(self.settings.power, lambda x: None, lambda x: None)
        llava_result = obj.run_llava(self.settings.power, image_path, self.settings.prompt.value)
        if not llava_result.is_op_ok():
            return Operation(status=False, error=llava_result.error)
        return Operation(status=True, payload=llava_result.payload)

