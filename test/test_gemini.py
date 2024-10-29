import unittest

from ai.util.ai_runner import AiRunner
from ai.core.ai_model_list import AiModelList
from ai.core.ai_power import AiPower
from ai.prompt.ai_prompts import AiPrompt
from ai.core.ai_setting import AiQuery
from ai.core.ai_source_type import AiSourceType
import sys
import os
from dotenv import load_dotenv

from util.pylizdir import PylizDir

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


class TestLmStudio(unittest.TestCase):

    def setUp(self):
        load_dotenv()
        print("Setting up test...")
        self.pyliz_dir = None


    def test1(self):
        self.pyliz_dir = PylizDir(".pyliztest")
        setting = AiQuery(
            model=AiModelList.GEMINI,
            source_type=AiSourceType.API_GEMINI,
            power=AiPower.LOW,
            payload_file_path=os.getenv('LOCAL_IMAGE_FOR_TEST'),
            api_key=os.getenv('GEMINI_API_KEY'),
            prompt="Analyze this image and tell me what you see."
        )
        result = AiRunner(self.pyliz_dir, setting).run()
        print("result status = " + str(result.status))
        print(result.payload)
        print("result error = " + result.error if result.error is not None else "No error")


    def test2(self):
        self.pyliz_dir = PylizDir(".pyliztest")
        setting = AiQuery(
            model=AiModelList.GEMINI,
            source_type=AiSourceType.API_GEMINI,
            power=AiPower.LOW,
            payload_file_path=os.getenv('LOCAL_VIDEO_FOR_TEST'),
            api_key=os.getenv('GEMINI_API_KEY'),
            prompt="Analyze this video and tell me what you see."
        )
        result = AiRunner(self.pyliz_dir, setting).run()
        print("result status = " + str(result.status))
        print(result.payload)
        print("result error = " + result.error if result.error is not None else "No error")






if __name__ == "__main__":
    unittest.main()