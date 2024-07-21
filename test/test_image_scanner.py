import os
import unittest

from dotenv import load_dotenv

from ai.model.ai_method import AiMethod
from ai.model.ai_model_list import AiModelList
from ai.model.ai_power import AiPower
from ai.model.ai_prompts import AiPrompt
from ai.model.ai_scan_settings import AiScanSettings
from ai.model.ai_setting import AiSettings
from ai.model.ai_source_type import AiSourceType
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
                source_type=AiSourceType.LOCAL_AI,
                power=AiPower.LOW,
                prompt=AiPrompt.LLAVA_JSON,
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