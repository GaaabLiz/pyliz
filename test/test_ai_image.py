


import os
import unittest

from ai.core.ai_model_list import AiModelList
from ai.core.ai_power import AiPower
from ai.core.ai_setting import AiSettings
from ai.core.ai_source_type import AiSourceType
from ai.llm.remote.service.lmstudioliz import LmStudioLiz
import sys
import os
from dotenv import load_dotenv

from ai.util.ai_runner import AiCustomRunner

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


class TestAiImage(unittest.TestCase):

    def setUp(self):
        load_dotenv()
        print("Setting up test...")


    def test1(self):
        image = os.getenv('LOCAL_IMAGE_FOR_TEST')
        api_key = os.getenv('MISTRAL_API_KEY')
        ai_image_setting = AiSettings(
            model=AiModelList.PIXSTRAL,
            source_type=AiSourceType.API_MISTRAL,
            power=AiPower.MEDIUM,
            api_key=api_key,
        )
        ai_text_setting = AiSettings(
            model=AiModelList.OPEN_MISTRAL,
            source_type=AiSourceType.API_MISTRAL,
            power=AiPower.LOW,
            api_key=api_key,
        )
        media = AiCustomRunner.run_for_image(ai_image_setting, ai_text_setting, image)



if __name__ == "__main__":
    unittest.main()