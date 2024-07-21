import os
import unittest

import rich

from ai.llm.llamacpp import LlamaCpp
from ai.model.ai_method import AiMethod
from ai.model.ai_power import AiPower
from ai.model.ai_scan_setting import AiSettings
from ai.prompts import prompt_llava_1
from media.image_scanner import ImageScanner
from util.pylizdir import PylizDir



class TestImageScanner(unittest.TestCase):

    def setUp(self):
        print("Setting up test...")

    def test_scan_image_with_llamacpp(self):
        try:
            path = "/Users/gabliz/Pictures/obama343434333.jpg"
            setting = AiSettings(
                method=AiMethod.LLAVA_LOCAL_LLAMACPP,
                power=AiPower.LOW,
                ai_tags=True,
                ai_file_metadata=True,
                ai_comment=True,
                ai_rename=True,
                ai_ocr=True
            )
            result = ImageScanner(path, setting).scan()
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