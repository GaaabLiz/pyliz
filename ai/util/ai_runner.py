import json
import os
import time
from typing import Callable

from loguru import logger

from ai.controller.gemini_controller import GeminiController
from ai.controller.mistral_controller import MistralController
from ai.llm.local.llamacpp import LlamaCpp
from ai.prompt.ai_prompts import AiPrompt
from ai.core.ai_setting import AiQuery
from ai.core.ai_source_type import AiSourceType
from media.liz_media import LizMedia
from model.operation import Operation
from util.jsonUtils import JsonUtils
from util.pylizdir import PylizDir


class AiRunner:

    def __init__(self, pyliz_dir: PylizDir, settings: AiQuery):
        self.ai = settings
        self.pyliz_dir = pyliz_dir
        self.folder_ai = self.pyliz_dir.get_folder_path("ai")
        self.folder_logs = self.pyliz_dir.get_folder_path("logs")
        self.model_folder = self.pyliz_dir.get_folder_path("models")

    def __handle_mistral(self) -> Operation[str]:
        controller = MistralController(self.ai.api_key)
        return controller.run(self.ai)

    def __handle_git_llama_cpp(self) -> Operation[str]:
        folder = os.path.join(self.folder_ai, "llama.cpp")
        logs = os.path.join(self.folder_logs, "llama.cpp")
        llama_cpp = LlamaCpp(folder, self.model_folder, logs)
        pass

    def __handle_gemini(self):
        controller = GeminiController(self.ai.api_key)
        return controller.run(self.ai)


    def run(self) -> Operation[str]:
        if self.ai.source_type == AiSourceType.API_MISTRAL:
            return self.__handle_mistral()
        if self.ai.source_type == AiSourceType.LOCAL_LLAMACPP:
            return self.__handle_git_llama_cpp()
        if self.ai.source_type == AiSourceType.API_GEMINI:
            return self.__handle_gemini()
        raise NotImplementedError("Source type not implemented yet in AiRunner")


class AiCustomRunner:

    @staticmethod
    def run_for_image(
            pyliz_dir: PylizDir,
            ai_image_setting: AiQuery,
            ai_text_setting: AiQuery,
            on_log: Callable[[str], None] = lambda x: None
    ) -> Operation[LizMedia]:
        # Image query
        on_log("Running image query")
        ai_image_result = AiRunner(pyliz_dir, ai_image_setting).run()
        logger.info(f"RunForMedia (image) result = {ai_image_result}")
        if not ai_image_result.status:
            return Operation(status=False, error=ai_image_result.error)
        # Text query
        on_log("Generating text")
        ai_text_result = AiRunner(pyliz_dir, ai_text_setting).run()
        logger.info(f"RunForMedia (text) result = {ai_text_result}")
        if not ai_text_result.status:
            return Operation(status=False, error=ai_text_result.error)
        # Media creation
        on_log("Generating object")
        time.sleep(0.5)
        media = LizMedia(ai_image_setting.payload_file_path)
        # Extract ai info from json
        on_log("Validating ai results")
        json_result_text = ai_text_result.payload
        if not JsonUtils.is_valid_json(json_result_text):
            return Operation(status=False, error="Ai returned an invalid json")
        if not JsonUtils.has_keys(json_result_text, ["text", "tags", "filename"]):
            return Operation(status=False, error="Ai returned json with missing keys")
        data = json.loads(json_result_text)
        media.ai_ocr_text = data['text']
        media.ai_description = ai_image_result.payload
        media.ai_tags = data['tags']
        media.ai_file_name = data['filename']
        media.ai_scanned = True
        time.sleep(0.5)
        on_log("Completed")
        return Operation(status=True, payload=media)