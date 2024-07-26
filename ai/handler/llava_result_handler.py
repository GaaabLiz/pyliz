import json

from ai.core.ai_prompts import AiPrompt
from ai.core.ai_scan_settings import AiScanSettings
from ai.core.ai_setting import AiSettings
from model.liz_image import LizImage
from model.operation import Operation


class LlavaResultHandler:

    def __init__(
            self,
            image_path: str,
            settings: AiSettings,
            result: Operation[str]
    ):
        self.settings = settings
        self.result = result
        self.image_path = image_path

    # def __handle_detailed_prompt(self) -> Operation[LizImage]:
    #     pass
    #
    # def get_operation_result(self) -> Operation[LizImage]:
    #     # if controller is not successful return error
    #     if not self.result.is_op_ok():
    #         return Operation(status=False, error=self.result.error)
    #     # format result from prompt type
    #     if self.settings.prompt == AiPrompt.LLAVA_JSON:
    #         return self.__get_image_from_json()
    #     elif self.settings.prompt == AiPrompt.LLAVA_DETAILED:
    #         return self.__handle_detailed_prompt()
    #     else:
    #         raise NotImplementedError("Prompt not implemented.")
