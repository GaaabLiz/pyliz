import rich

from ai.controller.mistral_controller import MistralController
from ai.core.ai_inputs import AiInputs
from ai.core.ai_prompts import AiPrompt
from ai.core.ai_setting import AiSettings
from ai.core.ai_source_type import AiSourceType
from media.liz_media import LizMedia
from model.operation import Operation


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
        ai_image_inputs = AiInputs(file_path=image_path, prompt=AiPrompt.VISION_DETAILED.value)
        ai_image_result = AiRunner(ai_image_setting, ai_image_inputs).run()
        rich.print(ai_image_result)
        if not ai_image_result.status:
            return Operation(status=False, error=ai_image_result.error)
        ai_text_inputs = AiInputs(prompt=AiPrompt.EXTRACT_INFO_FROM_VISION_QUERY_JSON.value + ai_image_result.payload)
        ai_text_result = AiRunner(ai_text_setting, ai_text_inputs).run()
        rich.print(ai_text_result)
        if not ai_text_result.status:
            return Operation(status=False, error=ai_text_result.error)
        media = LizMedia(image_path)
        return Operation(status=True, payload=media)