import json
import time
from typing import Callable

from loguru import logger

from ai.core.ai_setting import AiSetting, AiQuery
from ai.prompt.ai_prompts import AiPrompt
from ai.util.ai_runner import AiRunner
from media.liz_media import LizMedia
from model.operation import Operation
from util import fileutils
from util.jsonUtils import JsonUtils
from util.pylizdir import PylizDir
from enum import Enum


class PixelRunnerMethod(Enum):
    DOUBLE_QUERY_WITH_TEXT_GEN = "DOUBLE_QUERY_WITH_TEXT_GEN"
    SINGLE_QUERY_ONLY_VISION = "SINGLE_QUERY_ONLY_VISION"


class AiPixelRunner:

    def __init__(
        self,
        pyliz_dir: PylizDir,
        image_method: PixelRunnerMethod,
        ai_image_setting: AiSetting,
        ai_text_setting: AiSetting | None = None
    ):
        self.pyliz_dir = pyliz_dir
        self.image_method = image_method
        self.ai_image_setting = ai_image_setting
        self.ai_text_setting = ai_text_setting

        if image_method == PixelRunnerMethod.DOUBLE_QUERY_WITH_TEXT_GEN and ai_text_setting is None:
            raise ValueError("ai_text_setting is required for DOUBLE_QUERY_WITH_TEXT_GEN in AiPixelRunner")


    def __exec_image_query(self, media_path: str, prompt: str) -> str:
        query = AiQuery(self.ai_image_setting, prompt, media_path)
        ai_image_result = AiRunner(self.pyliz_dir, query).run()
        if not ai_image_result.status:
            raise ValueError(ai_image_result.error)
        logger.info(f"RunForMedia (image) result = {ai_image_result}")
        return ai_image_result.payload

    def __exec_text_query(self, prompt: str) -> str:
        ai_text_result = AiRunner(self.pyliz_dir, AiQuery(self.ai_text_setting, prompt)).run()
        logger.info(f"RunForMedia (text) result = {ai_text_result}")
        if not ai_text_result.status:
            raise ValueError(ai_text_result.error)
        return ai_text_result.payload

    def __handle_image_with_text_gen(
            self,
            media_path: str,
            on_log: Callable[[str], None] = lambda x: None
    ) -> Operation[LizMedia]:
        try:
            # Image query
            on_log("Running image query")
            ai_image_result = self.__exec_image_query(media_path, AiPrompt.IMAGE_VISION_DETAILED_1.value)
            # Text query
            on_log("Generating text")
            ai_text_result = self.__exec_text_query(AiPrompt.TEXT_EXTRACT_FROM_VISION_1.value + ai_image_result)
            # Media creation
            on_log("Generating object")
            time.sleep(0.5)
            media = LizMedia(media_path)
            # Extract ai info from json
            on_log("Validating ai results")
            json_result_text = ai_text_result
            if not JsonUtils.is_valid_json(json_result_text):
                raise ValueError("Ai returned invalid json")
            if not JsonUtils.has_keys(json_result_text, ["text", "tags", "filename"]):
                raise ValueError("Ai returned invalid json keys")
            data = json.loads(json_result_text)
            media.ai_ocr_text = data['text']
            media.ai_description = ai_image_result
            media.ai_tags = data['tags']
            media.ai_file_name = data['filename']
            media.ai_scanned = True
            time.sleep(0.5)
            on_log("Completed")
            return Operation(status=True, payload=media)
        except Exception as e:
            return Operation(status=False, error=str(e))


    def __handle_image_only_vision(self, media_path: str, on_log: Callable[[str], None] = lambda x: None) -> Operation[LizMedia]:
        try:
            # Image query
            on_log("Running image query")
            ai_image_result = self.__exec_image_query(media_path, AiPrompt.IMAGE_VISION_JSON.value)
            logger.info(f"RunForMedia (image) result = {ai_image_result}")
            raise NotImplementedError("Image only vision not implemented yet in AiPixelRunner")
        except Exception as e:
            return Operation(status=False, error=str(e))



    def __run_image(
            self,
            media_path: str,
            on_log: Callable[[str], None] = lambda x: None
    ) -> Operation[LizMedia]:
        if self.image_method == PixelRunnerMethod.DOUBLE_QUERY_WITH_TEXT_GEN:
            return self.__handle_image_with_text_gen(media_path, on_log)
        elif self.image_method == PixelRunnerMethod.SINGLE_QUERY_ONLY_VISION:
            return self.__handle_image_only_vision(media_path, on_log)
        else:
            raise ValueError("Unsupported image_method in AiPixelRunner")

    def __run_video(self, media_path: str, on_log: Callable[[str], None] = lambda x: None) -> Operation[LizMedia]:
        raise NotImplementedError("Video not implemented yet in AiPixelRunner")


    def scan(
            self,
            media_path: str,
            on_log: Callable[[str], None] = lambda x: None
    ) -> Operation[LizMedia]:
        if fileutils.is_image_file(media_path):
            return self.__run_image(media_path, on_log)
        elif fileutils.is_video_file(media_path):
            return self.__run_video(media_path, on_log)
        else:
            raise ValueError("Unsupported file type in AiPixelRunner")


