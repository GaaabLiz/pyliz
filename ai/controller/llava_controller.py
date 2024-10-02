import base64
import json
import os

from ai.core.ai_method import AiMethod
from ai.core.ai_prompts import AiPrompt
from ai.core.ai_scan_settings import AiScanSettings
from ai.core.ai_setting import AiSettings
from ai.core.ai_source_type import AiSourceType
from ai.llm.local.llamacpp import LlamaCpp
from ai.llm.remote.service.ollamaliz import Ollamaliz
from model.liz_image import LizImage
from model.operation import Operation
from util.pylizdir import PylizDir


class LlavaController:

    def __init__(self, settings: AiSettings, rag_settings: AiSettings | None = None):
        self.settings = settings
        self.rag_settings = rag_settings

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
        return Operation(status=False, error="Not implemented yet.")

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

    def __get_image_from_json(self, output: str, image_path: str) -> Operation[LizImage]:
        info_json = json.loads(output)
        output_image = LizImage(image_path)
        output_image.set_ai_filename(info_json.get("filename")) if self.settings.scan_settings.ai_rename else None
        output_image.set_ai_description(info_json.get("description")) if self.settings.scan_settings.ai_comment else None
        output_image.set_ai_tags(info_json.get("tags")) if self.settings.scan_settings.ai_tags else None
        output_image.set_ai_text(info_json.get("text")) if self.settings.scan_settings.ai_ocr else None
        output_image.set_ai_scanned(True)
        return Operation(status=True, payload=output_image)


    # def run(self, image_path: str) -> Operation[str]:
    #     if self.settings.method == AiMethod.LLAVA_OLLAMA:
    #         return self.__run_from_ollama(image_path)
    #     elif self.settings.method == AiMethod.LLAVA_LOCAL_LLAMACPP:
    #         return self.__run_from_local_llamacpp(image_path)
    #     else:
    #         raise NotImplementedError("This method is not implemented.")


    # def run_and_get_liz_media(self, image_path: str) -> Operation[LizImage]:
    #     if self.settings.prompt == AiPrompt.LLAVA_INNER_JSON:
    #         op = self.__run_from_ollama(image_path)
    #         if not op.is_op_ok():
    #             return Operation(status=False, error=op.error)
    #         return self.__get_image_from_json(op.payload, image_path)
    #     elif self.settings.method == AiMethod.LLAVA_INNER_JSON:
    #         op = self.__run_from_local_llamacpp(image_path)
    #         if not op.is_op_ok():
    #             return Operation(status=False, error=op.error)
    #         return self.__get_image_from_json(op.payload, image_path)
    #     else:
    #         raise NotImplementedError("Current Aimethod is not implemented for this function.")


    def run_and_get_liz_media(
            self,
            image_path: str,
            scan_settings: AiScanSettings | None = None
    ) -> Operation[LizImage]:
        if self.rag_settings is None:
            raise ValueError("Rag AI settings is not set.")

    def run_and_get_vanilla_json(self, image_path: str, prompt: str) -> Operation[str]:
        if self.settings.source_type == AiSourceType.LMSTUDIO_SERVER:
            return self.__run_from_lm_studio(image_path, prompt)
        elif self.settings.source_type == AiSourceType.OLLAMA_SERVER:
            return self.__run_from_ollama(image_path, prompt)
        elif self.settings.source_type == AiSourceType.LOCAL_LLAMACPP:
            return self.__run_from_local_llamacpp(image_path, prompt)
        else:
            raise NotImplementedError("This source type for llava is not implemented.")