import base64
import os

from ai.core.ai_setting import AiSetting
from ai.core.ai_source_type import AiSourceType
from ai.llm.local.llamacpp import LlamaCpp
from ai.llm.remote.service.lmstudioliz import LmStudioLiz
from ai.llm.remote.service.ollamaliz import Ollamaliz
from model.operation import Operation
from old_code.pylizdir_OLD import PylizDir


class LlavaController:

    def __init__(self, settings: AiSetting):
        self.settings = settings

    def __run_from_ollama(self, image_path: str, prompt: str) -> Operation[str]:
        ollama = Ollamaliz(self.settings.remote_url)
        model_name = self.settings.source.ollama_name
        with open(image_path, "rb") as image_file:
            image_base_64 = base64.b64encode(image_file.read()).decode('utf-8')
        llava_result = ollama.llava_query(prompt, image_base_64, model_name)
        if not llava_result.is_op_ok():
            return Operation(status=False, error=llava_result.error)
        return Operation(status=True, payload=llava_result.payload.response)

    def __run_from_lm_studio(self, image_path: str, prompt: str) -> Operation[str]:
        lm_studio = LmStudioLiz(self.settings.remote_url)
        model_name = self.settings.source.lmstudio_name
        try:
            if not lm_studio.has_model_loaded(model_name):
                return Operation(status=False, error=f"Model {model_name} is not loaded in LM Studio.")
            with open(image_path, "rb") as image_file:
                image_base_64 = base64.b64encode(image_file.read()).decode('utf-8')
            response = lm_studio.send_vision_prompt(image_base_64, prompt)
            return Operation(status=True, payload=response)
        except Exception as e:
            return Operation(status=False, error=str(e))


    def __run_from_local_llamacpp(self, image_path: str, prompt: str) -> Operation[str]:
        PylizDir.create()
        path_install: str = os.path.join(PylizDir.get_ai_folder(), "llama.cpp")
        path_models: str = PylizDir.get_models_folder()
        path_logs: str = os.path.join(PylizDir.get_logs_path(), "llama.cpp")
        obj = LlamaCpp(path_install, path_models, path_logs)
        obj.install_llava(self.settings.power, lambda x: None, lambda x: None)
        llava_result = obj.run_llava(self.settings.power, image_path, prompt)
        if not llava_result.is_op_ok():
            return Operation(status=False, error=llava_result.error)
        return Operation(status=True, payload=llava_result.payload)


    # def get_liz_media_from_json(self, output: str) -> Operation[LizMedia]:
    #     raise NotImplementedError("This method is not implemented.")


    def run_and_get_vanilla_json(self, image_path: str, prompt: str) -> Operation[str]:
        if self.settings.source_type == AiSourceType.LMSTUDIO_SERVER:
            return self.__run_from_lm_studio(image_path, prompt)
        elif self.settings.source_type == AiSourceType.OLLAMA_SERVER:
            return self.__run_from_ollama(image_path, prompt)
        elif self.settings.source_type == AiSourceType.LOCAL_LLAMACPP:
            return self.__run_from_local_llamacpp(image_path, prompt)
        else:
            raise NotImplementedError("This source type for llava is not implemented.")