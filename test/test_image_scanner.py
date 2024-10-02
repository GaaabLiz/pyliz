import os
import unittest

from dotenv import load_dotenv

from ai.core.ai_model_list import AiModelList
from ai.core.ai_power import AiPower
from ai.core.ai_prompts import AiPrompt
from ai.core.ai_scan_settings import AiScanSettings
from ai.core.ai_setting import AiSettings
from ai.core.ai_source_type import AiSourceType
from media.image_scanner import ImageScanner


class TestImageScanner(unittest.TestCase):

    def setUp(self):
        load_dotenv()
        self.test_image = os.getenv("LOCAL_IMAGE_FOR_TEST")
        print("Setting up test...")

    def test_scan_image_with_llamacpp(self):
        try:
            scan_settings = AiScanSettings(True, True, True, True, True)
            ai_settings = AiSettings(
                model=AiModelList.LLAVA,
                source_type=AiSourceType.LOCAL_LLAMACPP,
                power=AiPower.LOW,
                prompt=AiPrompt.LLAVA_INNER_JSON,
                scan_settings=scan_settings
            )
            result = ImageScanner(self.test_image, ai_settings).scan()
            self.assertTrue(result.status)
            if result.status:
                image = result.payload
                print(image.ai_description)
            else:
                raise Exception(result.error)
        except Exception as e:
            self.fail(e)


if __name__ == "__main__":
    unittest.main()