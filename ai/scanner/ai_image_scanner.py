import json
from enum import Enum
from typing import Callable

from loguru import logger

from ai.core.ai_setting import AiSetting
from ai.model.ai_payload_info import AiPayloadMediaInfo
from ai.prompt.ai_prompts import AiPrompt
from ai.runner.ai_common_runner import AiCommonRunner
from util.jsonUtils import JsonUtils
from util.pylizdir import PylizDir


class AiImageScanningType(Enum):
    DOUBLE_QUERY_WITH_TEXT_GEN = "DOUBLE_QUERY_WITH_TEXT_GEN"
    SINGLE_QUERY_ONLY_VISION = "SINGLE_QUERY_ONLY_VISION"


class AiImageScanner:

    def __init__(self, pyliz_dir: PylizDir, scanning_type: AiImageScanningType):
        self.pyliz_dir = pyliz_dir
        self.scanning_type = scanning_type

    def run(
            self,
            path: str,
            ai_image_setting: AiSetting,
            ai_text_setting: AiSetting | None = None
    ) -> AiPayloadMediaInfo:
        logger.debug(f"Running image scanner with {self.scanning_type}")
        if self.scanning_type == AiImageScanningType.DOUBLE_QUERY_WITH_TEXT_GEN:
            obj = self.RunnerWithTextGen(self.pyliz_dir, ai_image_setting, ai_text_setting)
            return obj.run(path)
        elif self.scanning_type == AiImageScanningType.SINGLE_QUERY_ONLY_VISION:
            raise NotImplementedError("Image only vision not implemented yet in AiPixelRunner")
        else:
            raise ValueError("Unsupported image_method in AiPixelRunner")


    class RunnerWithTextGen:

        def __init__(
                self,
                pyliz_dir: PylizDir,
                ai_image_setting: AiSetting,
                ai_text_setting: AiSetting | None = None,
        ):
            self.pyliz_dir = pyliz_dir
            self.ai_image_setting = ai_image_setting
            self.ai_text_setting = ai_text_setting

        @staticmethod
        def extract_json_info( ai_text_result: str) -> AiPayloadMediaInfo:
            logger.debug(f"Extracting json info from ai_text_result...")
            json_result_text = ai_text_result
            if not JsonUtils.is_valid_json(json_result_text):
                raise ValueError("Ai returned invalid json")
            if not JsonUtils.has_keys(json_result_text, ["text", "tags", "filename"]):
                raise ValueError("Ai returned invalid json keys")
            try:
                data = json.loads(json_result_text)
            except json.JSONDecodeError:
                raise ValueError("Unable to decode json")
            ai_info = AiPayloadMediaInfo(
                text=data['text'],
                tags=data['tags'],
                filename=data['filename'],
                description=ai_text_result,
            )
            return ai_info

        def run(self, path: str) -> AiPayloadMediaInfo:
            logger.debug(f"RunnerWithTextGen running image query...")
            ai_image_result = AiCommonRunner.run_query(self.pyliz_dir, self.ai_image_setting, AiPrompt.IMAGE_VISION_DETAILED_1.value, path, )
            prompt_text = AiPrompt.TEXT_EXTRACT_FROM_VISION_1.value + ai_image_result
            logger.debug(f"RunnerWithTextGen running text query...")
            ai_text_result = AiCommonRunner.run_query(self.pyliz_dir, self.ai_text_setting, prompt_text)
            return AiImageScanner.RunnerWithTextGen.extract_json_info(ai_text_result)



