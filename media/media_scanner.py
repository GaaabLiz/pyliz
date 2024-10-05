from ai.controller.llava_controller import LlavaController
from ai.core.ai_prompts import AiPrompt
from ai.core.ai_setting import AiSettings
from model.liz_media import LizMedia
from model.operation import Operation


class MediaScanner:

    def __init__(
        self,
        path: str,
        image_ai_setting: AiSettings | None = None,
        rag_ai_setting: AiSettings | None = None
    ):
        self.path = path
        self.image_ai_setting = image_ai_setting
        self.rag_ai_setting = rag_ai_setting

    def scan_media_without_ai(self) -> LizMedia:
        return LizMedia(self.path)

    def scan_with_llava(self) -> Operation[LizMedia]:
        if self.image_ai_setting is None or self.rag_ai_setting is None:
            raise ValueError("Ai settings are not set for this operation. Check the constructor.")
        controller = LlavaController(self.image_ai_setting, self.rag_ai_setting)
        json_result_operation = controller.run_and_get_vanilla_json(self.path, AiPrompt.LLAVA_DETAILED.value)
        if not json_result_operation.status:
            return Operation(status=False, error=json_result_operation.error)
        liz_media_operation = controller.get_liz_media_from_json(json_result_operation.payload)
        if not liz_media_operation.status:
            return Operation(status=False, error=liz_media_operation.error)
        return Operation(status=True, payload=liz_media_operation.payload)
