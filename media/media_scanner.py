from ai.model.ai_method import AiMethod
from ai.model.ai_scan_setting import AiSettings
from model.liz_image import LizImage
from model.operation import Operation


def scan_image(
        path: str,
        setting: AiSettings | None = None,
) -> Operation[LizImage]:
    # if ai not provided, return LizImage object
    if not setting:
        return Operation(status=True, payload=LizImage(path))
    # Scanning image with ai_method
    if setting.method == AiMethod.LLAVA_OLLAMA:
        llava_result = scan_image_with_llava(file_path)
    else:
        raise ValueError("ai_method not supported.")


