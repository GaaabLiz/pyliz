import base64
import json
import os

from ai.llm.llamacpp import LlamaCpp
from ai.model.ai_method import AiMethod
from ai.model.ai_models import AiModels
from ai.model.ai_scan_setting import AiSettings
from ai.prompts import prompt_llava_1
from api.service.ollamaliz import Ollamaliz
from model.liz_image import LizImage
from model.operation import Operation
from util.pylizdir import PylizDir


class ImageScanner:

    def __init__(self, path: str, settings: AiSettings | None = None):
        self.path = path
        self.settings = settings

    def scan(self) -> Operation[LizImage]:
        if self.settings:
            return self.__scan_image_with_ai()
        else:
            return self.__scan_image()

    def __scan_image_with_ai(self) -> Operation[LizImage]:
        if self.settings.method == AiMethod.LLAVA_OLLAMA:
            return self.__scan_image_with_llava_ollama()
        elif self.settings.method == AiMethod.LLAVA_LOCAL_LLAMACPP:
            return self.__scan_image_with_llamacpp()
        else:
            raise NotImplementedError("AI method not implemented.")

    def __scan_image(self) -> Operation[LizImage]:
        return Operation(status=True, payload=LizImage(self.path))

    def __scan_image_with_llava_ollama(self) -> Operation[LizImage]:
        ollamaliz = Ollamaliz(self.settings.remote_url)
        model_name = AiModels.get_llava(self.settings.power, AiMethod.LLAVA_OLLAMA).ollama_name
        with open(self.path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
        llava_result = ollamaliz.llava_query(prompt_llava_1, encoded_string, model_name)
        if not llava_result.status:
            return Operation(status=False, error=llava_result.error)
        return self.__create_image_from_llava_json(llava_result.payload.response)

    def __scan_image_with_llamacpp(self) -> Operation[LizImage]:
        PylizDir.create()
        path_install: str = os.path.join(PylizDir.get_ai_folder(), "llama.cpp")
        path_models: str = PylizDir.get_models_folder()
        path_logs: str = os.path.join(PylizDir.get_logs_path(), "llama.cpp")
        obj = LlamaCpp(path_install, path_models, path_logs)
        obj.install_llava(self.settings.power, lambda x: None, lambda x: None)
        result = obj.run_llava(self.settings.power, self.path, prompt_llava_1)
        return self.__create_image_from_llava_json(result)

    def __create_image_from_llava_json(self, json_string: str) -> Operation[LizImage]:
        info_json = json.loads(json_string)
        output_image = LizImage(self.path)
        output_image.set_ai_filename(info_json.get("filename")) if self.settings.ai_rename else None
        output_image.set_ai_description(info_json.get("description")) if self.settings.ai_comment else None
        output_image.set_ai_tags(info_json.get("tags")) if self.settings.ai_tags else None
        output_image.set_ai_text(info_json.get("text")) if self.settings.ai_ocr else None
        output_image.set_ai_scanned(True)
        return Operation(status=True, payload=output_image)