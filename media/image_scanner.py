import base64
import os

from ai.controller.llava_controller import LlavaController
from ai.core.ai_prompts import AiPrompt
from ai.handler.llava_result_handler import LlavaResultHandler
from ai.llm.local.llamacpp import LlamaCpp
from ai.core.ai_method import AiMethod
from ai.core.ai_setting import AiSettings
from ai.llm.remote.service.ollamaliz import Ollamaliz
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
        result = LlavaController(self.settings).run_from_ollama(self.path)
        handler = LlavaResultHandler(self.path, self.settings, result)
        return handler.get_operation_result()

    def __scan_image_with_llamacpp(self) -> Operation[LizImage]:
        result = LlavaController(self.settings).run_from_local_llamacpp(self.path)
        handler = LlavaResultHandler(self.path, self.settings, result)
        return handler.get_operation_result()



