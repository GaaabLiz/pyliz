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
        controller = LlavaController(self.settings)
        return controller.run_and_get_liz_media(self.path)

    def __scan_image(self) -> Operation[LizImage]:
        return Operation(status=True, payload=LizImage(self.path))





