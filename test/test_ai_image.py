


import os
import unittest

import rich

from ai.core.ai_model_list import AiModelList
from ai.core.ai_power import AiPower
from ai.core.ai_setting import AiSetting
from ai.core.ai_source_type import AiSourceType
from ai.llm.remote.service.lmstudioliz import LmStudioLiz
import sys
import os
from dotenv import load_dotenv

from ai.util.ai_pixel_runner import AiPixelRunner, PixelRunnerMethod
from util import pylizLogging
from util.pylizdir import PylizDir

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


class TestAiImage(unittest.TestCase):

    def setUp(self):
        load_dotenv()
        pylizLogging.enable_logging("DEBUG", None, True)
        print("Setting up test...")


    def test1(self):
        pyliz_dir = PylizDir(".pyliztest")
        image = os.getenv('LOCAL_IMAGE_FOR_TEST')
        api_key = os.getenv('MISTRAL_API_KEY')
        ai_image_setting = AiSetting(
            model=AiModelList.PIXSTRAL,
            source_type=AiSourceType.API_MISTRAL,
            power=AiPower.MEDIUM,
            api_key=api_key,
        )
        ai_text_setting = AiSetting(
            model=AiModelList.OPEN_MISTRAL,
            source_type=AiSourceType.API_MISTRAL,
            power=AiPower.LOW,
            api_key=api_key,
        )
        pixel_runner = AiPixelRunner(pyliz_dir, PixelRunnerMethod.DOUBLE_QUERY_WITH_TEXT_GEN, ai_image_setting, ai_text_setting)
        media = pixel_runner.scan(image)
        rich.print("----")
        rich.print(media.payload.ai_description)
        rich.print(media.payload.ai_file_name)
        rich.print("end")


    def test2(self):
        pyliz_dir = PylizDir(".pyliztest")
        image = os.getenv('LOCAL_IMAGE_FOR_TEST')
        api_key = os.getenv('MISTRAL_API_KEY')
        ai_image_setting = AiSetting(
            model=AiModelList.PIXSTRAL,
            source_type=AiSourceType.API_MISTRAL,
            power=AiPower.MEDIUM,
            api_key=api_key,
        )
        ai_text_setting = AiSetting(
            model=AiModelList.OPEN_MISTRAL,
            source_type=AiSourceType.API_MISTRAL,
            power=AiPower.LOW,
            api_key=api_key,
        )
        pixel_runner = AiPixelRunner(pyliz_dir, PixelRunnerMethod.DOUBLE_QUERY_WITH_TEXT_GEN, ai_image_setting, ai_text_setting)
        media = pixel_runner.test()



if __name__ == "__main__":
    unittest.main()