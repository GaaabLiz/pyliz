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

    def __handle_json_prompt(self) -> Operation[LizImage]:
        output = self.result.payload
        info_json = json.loads(output)
        output_image = LizImage(self.image_path)
        output_image.set_ai_filename(info_json.get("filename")) if self.settings.scan_settings.ai_rename else None
        output_image.set_ai_description(info_json.get("description")) if self.settings.scan_settings.ai_comment else None
        output_image.set_ai_tags(info_json.get("tags")) if self.settings.scan_settings.ai_tags else None
        output_image.set_ai_text(info_json.get("text")) if self.settings.scan_settings.ai_ocr else None
        output_image.set_ai_scanned(True)
        return Operation(status=True, payload=output_image)

    def __handle_detailed_prompt(self) -> Operation[LizImage]:
        pass

    def get_operation_result(self) -> Operation[LizImage]:
        # if controller is not successful return error
        if not self.result.is_op_ok():
            return Operation(status=False, error=self.result.error)
        # format result from prompt type
        if self.settings.prompt == AiPrompt.LLAVA_JSON:
            return self.__handle_json_prompt()
        elif self.settings.prompt == AiPrompt.LLAVA_DETAILED:
            return self.__handle_detailed_prompt()
        else:
            raise NotImplementedError("Prompt not implemented.")
