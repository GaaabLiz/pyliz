import json

from ai.core.ai_prompts import AiPrompt
from ai.core.ai_scan_settings import AiScanSettings
from ai.core.ai_setting import AiSettings
from model.liz_image import LizImage
from model.operation import Operation


class LlavaResultHandler:

    def __init__(self, settings: AiSettings):
        self.settings = settings

    def get_image_from_json(
            self,
            output: str,
            image_path: str,
            scan_settings: AiScanSettings
    ) -> Operation[LizImage]:
        if self.settings.prompt != AiPrompt.LLAVA_JSON:
            raise Exception("Invalid prompt for LlavaAdapter adapter.")
        info_json = json.loads(output)
        output_image = LizImage(image_path)
        output_image.set_ai_filename(info_json.get("filename")) if scan_settings.ai_rename else None
        output_image.set_ai_description(info_json.get("description")) if scan_settings.ai_comment else None
        output_image.set_ai_tags(info_json.get("tags")) if scan_settings.ai_tags else None
        output_image.set_ai_text(info_json.get("text")) if scan_settings.ai_ocr else None
        output_image.set_ai_scanned(True)
        return Operation(status=True, payload=output_image)

