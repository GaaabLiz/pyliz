import rich
from loguru import logger

from ai.core.ai_setting import AiSetting
from ai.scanner.ai_image_scanner import AiImageScanner, AiImageScanningType
from media.liz_media import LizMedia
from model.operation import Operation
from util import fileutils
from util.pylizdir import PylizDir
import tracemalloc


class AiMediaScanner:

    def __init__(self, pyliz_dir: PylizDir):
        self.pyliz_dir = pyliz_dir

    def scan_image(
            self,
            path: str,
            scanning_type: AiImageScanningType,
            ai_image: AiSetting,
            ai_text: AiSetting | None = None
    ) -> Operation[LizMedia]:
        if not fileutils.is_image_file(path):
            return Operation(status=False, error=f"Path {path} is not an image file.")
        try:
            logger.info(f"Scanning image {path} with {scanning_type}")
            media = LizMedia(path)
            scanner = AiImageScanner(self.pyliz_dir, scanning_type)
            ai_info = scanner.run(path, ai_image, ai_text)
            media.apply_ai_info(ai_info)
            return Operation(status=True, payload=media)
        except Exception as e:
            return Operation(status=False, error=str(e))

