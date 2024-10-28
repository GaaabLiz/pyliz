import json

from loguru import logger

from ai.controller.mistral_controller import MistralController
from ai.core.ai_inputs import AiInputs
from ai.prompt.ai_prompts import AiPrompt
from ai.core.ai_setting import AiSettings
from ai.core.ai_source_type import AiSourceType
from media.liz_media import LizMedia
from model.operation import Operation
from util.jsonUtils import JsonUtils


class AiRunner:

    def __init__(self, settings: AiSettings, inputs: AiInputs):
        self.ai = settings
        self.inputs = inputs

    def __handle_mistral(self) -> Operation[str]:
        controller = MistralController(self.ai.api_key)
        return controller.run(self.ai, self.inputs.prompt, self.inputs.file_path)


    def run(self) -> Operation[str]:
        if self.ai.source_type == AiSourceType.API_MISTRAL:
            return self.__handle_mistral()
        raise NotImplementedError("Source type not implemented yet in AiRunner")


class AiCustomRunner:

    @staticmethod
    def run_for_image(ai_image_setting: AiSettings, ai_text_setting, image_path: str) -> Operation[LizMedia]:
        # Image query
        ai_image_inputs = AiInputs(file_path=image_path, prompt=AiPrompt.IMAGE_VISION_DETAILED_1.value)
        ai_image_result = AiRunner(ai_image_setting, ai_image_inputs).run()
        logger.info(ai_image_result)
        if not ai_image_result.status:
            return Operation(status=False, error=ai_image_result.error)
        # Text query
        ai_text_inputs = AiInputs(prompt=AiPrompt.TEXT_EXTRACT_FROM_VISION_1.value + ai_image_result.payload)
        ai_text_result = AiRunner(ai_text_setting, ai_text_inputs).run()
        logger.info(ai_text_result)
        if not ai_text_result.status:
            return Operation(status=False, error=ai_text_result.error)
        # Media creation
        media = LizMedia(image_path)
        # Extract ai info from json
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
        return Operation(status=True, payload=media)