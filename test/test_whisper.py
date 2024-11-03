import unittest

from ai.runner.ai_runner import AiRunner
from ai.core.ai_model_list import AiModelList
from ai.core.ai_power import AiPower
from ai.core.ai_setting import AiSetting, AiQuery
from ai.core.ai_source_type import AiSourceType
import sys
import os
from dotenv import load_dotenv

from util import pylizLogging
from util.pylizdir import PylizDir, PylizDirFoldersTemplate

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


class TestWhisper(unittest.TestCase):

    def setUp(self):
        load_dotenv()
        print("Setting up test...")
        pylizLogging.enable_logging("DEBUG", None, True)
        self.pyliz_dir = PylizDir(".pyliztest")
        self.pyliz_dir.add_all_template_folders()


    def test1(self):
        setting = AiSetting(
            model=AiModelList.WHISPER,
            source_type=AiSourceType.LOCAL_WHISPER,
            power=AiPower.MEDIUM
        )
        query = AiQuery(setting=setting, prompt=None, payload_path=os.getenv("LOCAL_VIDEO_2_FOR_TEST"))
        result = AiRunner(self.pyliz_dir).run(query)
        print("result status = " + str(result.status))
        print(result.payload)
        print("result error = " + result.error if result.error is not None else "No error")


    def test2(self):
        self.pyliz_dir = PylizDir(".pyliztest")
        setting = AiSetting(
            model=AiModelList.GEMINI,
            source_type=AiSourceType.API_GEMINI,
            power=AiPower.LOW,
            api_key=os.getenv('GEMINI_API_KEY'),
        )
        query = AiQuery(setting=setting, prompt="Analyze this video and tell what you see", payload_path=os.getenv("LOCAL_VIDEO_FOR_TEST"))
        result = AiRunner(self.pyliz_dir, query).run()
        print("result status = " + str(result.status))
        print(result.payload)
        print("result error = \n" + result.error if result.error is not None else "No error")





if __name__ == "__main__":
    unittest.main()