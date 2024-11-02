import json
import time
from typing import Callable

from loguru import logger

from ai.core.ai_model_list import AiModelList
from ai.core.ai_setting import AiSetting, AiQuery
from ai.prompt.ai_prompts import AiPrompt
from ai.util.ai_runner import AiRunner
from media.liz_media import LizMedia
from model.operation import Operation
from util import fileutils, datautils
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
        ai_text_setting: AiSetting | None = None,
        on_log: Callable[[str], None] = lambda x: None
    ):
        self.pyliz_dir = pyliz_dir
        self.image_method = image_method
        self.ai_image_setting = ai_image_setting
        self.ai_text_setting = ai_text_setting
        self.on_log = on_log

        if image_method == PixelRunnerMethod.DOUBLE_QUERY_WITH_TEXT_GEN and ai_text_setting is None:
            raise ValueError("ai_text_setting is required for DOUBLE_QUERY_WITH_TEXT_GEN in AiPixelRunner")


    def scan(self, media_path: str) -> Operation[LizMedia]:
        if self.image_method == PixelRunnerMethod.DOUBLE_QUERY_WITH_TEXT_GEN:
            obj = self._RunnerWithTextGen(self.pyliz_dir, self.ai_image_setting, self.ai_text_setting, self.on_log)
            return obj.run(media_path)
        elif self.image_method == PixelRunnerMethod.SINGLE_QUERY_ONLY_VISION:
            raise NotImplementedError("Image only vision not implemented yet in AiPixelRunner")
        else:
            raise ValueError("Unsupported image_method in AiPixelRunner")


    class Common:

        @staticmethod
        def log(message: str, on_log: Callable[[str], None] = lambda x: None, ):
            if on_log is not None:
                on_log(message)

        @staticmethod
        def run_query(pyliz_dir: PylizDir, ai_setting: AiSetting, prompt: str, media_path: str | None = None) -> str:
            query = AiQuery(ai_setting, prompt, media_path)
            ai_result = AiRunner(pyliz_dir).run(query)
            if not ai_result.status:
                raise ValueError(ai_result.error)
            logger.info(f"RunForMedia (pixel) result = {ai_result}")
            return ai_result.payload


    class _RunnerWithTextGen:

        def __init__(
                self,
                pyliz_dir: PylizDir,
                ai_image_setting: AiSetting,
                ai_text_setting: AiSetting | None = None,
                on_log: Callable[[str], None] = lambda x: None
        ):
            self.pyliz_dir = pyliz_dir
            self.ai_image_setting = ai_image_setting
            self.ai_text_setting = ai_text_setting
            self.on_log = on_log

        def __convert_pixel_result_to_liz_media(self, path: str, ai_pixel_result: str) -> LizMedia:
            # Text query
            AiPixelRunner.Common.log("Generating text", self.on_log)
            prompt_text = AiPrompt.TEXT_EXTRACT_FROM_VISION_1.value + ai_pixel_result
            ai_text_result = AiPixelRunner.Common.run_query(self.pyliz_dir, self.ai_text_setting, prompt_text)
            # Media creation
            AiPixelRunner.Common.log("Generating object", self.on_log)
            time.sleep(0.5)
            media = LizMedia(path)
            # Extract ai info from json
            AiPixelRunner.Common.log("Validating result", self.on_log)
            json_result_text = ai_text_result
            if not JsonUtils.is_valid_json(json_result_text):
                raise ValueError("Ai returned invalid json")
            if not JsonUtils.has_keys(json_result_text, ["text", "tags", "filename"]):
                raise ValueError("Ai returned invalid json keys")
            data = json.loads(json_result_text)
            media.ai_ocr_text = data['text']
            media.ai_description = ai_pixel_result
            media.ai_tags = data['tags']
            media.ai_file_name = data['filename']
            media.ai_scanned = True
            time.sleep(0.5)
            AiPixelRunner.Common.log("completed", self.on_log)
            return media

        def __run_image(self, path: str) -> Operation[LizMedia]:
            try:
                # Image query
                AiPixelRunner.Common.log("Running image query", self.on_log)
                ai_image_result = AiPixelRunner.Common.run_query(self.pyliz_dir, self.ai_image_setting, AiPrompt.IMAGE_VISION_DETAILED_1.value, path, )
                media = self.__convert_pixel_result_to_liz_media(path, ai_image_result)
                return Operation(status=True, payload=media)
            except Exception as e:
                return Operation(status=False, error=str(e))

        def __run_video(self, path: str) -> Operation[LizMedia]:
            current_model = self.ai_image_setting.model
            allowed_video_model = [AiModelList.GEMINI]
            if not datautils.contains_item(current_model, allowed_video_model):
                raise Exception(f"Model {current_model} is not allowed for video analysis")
            try:
                AiPixelRunner.Common.log("Running video query", self.on_log)
                ai_video_result = AiPixelRunner.Common.run_query(self.pyliz_dir, self.ai_image_setting, AiPrompt.IMAGE_VISION_DETAILED_1.value, path)
                media = self.__convert_pixel_result_to_liz_media(path, ai_video_result)
                return Operation(status=True, payload=media)
            except Exception as e:
                return Operation(status=False, error=str(e))

        def run(self, path: str) -> Operation[LizMedia]:
            if fileutils.is_image_file(path):
                return self.__run_image(path)
            elif fileutils.is_video_file(path):
                return self.__run_video(path)
            else:
                raise ValueError("Unsupported file type in AiPixelRunner")



    class _RunnerOnlyVision:

        def __init__(self, path: str):
            self.path = path


        def run(self) -> Operation[LizMedia]:
            pass





