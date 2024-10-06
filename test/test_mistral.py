
import os
import unittest

from ai.controller.mistral_controller import MistralController
from ai.core.ai_model_list import AiModelList
from ai.core.ai_power import AiPower
from ai.core.ai_setting import AiSettings
from ai.core.ai_source_type import AiSourceType
from ai.llm.remote.service.lmstudioliz import LmStudioLiz
import sys
import os
from dotenv import load_dotenv
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


class TestLmStudio(unittest.TestCase):

    def setUp(self):
        load_dotenv()
        print("Setting up test...")


    def test1(self):
        setting = AiSettings(
            model=AiModelList.OPEN_MISTRAL,
            source_type=AiSourceType.API_MISTRAL,
            power=AiPower.LOW
        )
        controller = MistralController(setting, os.getenv('MISTRAL_API_KEY'))
        result = controller.run_open_mistral("Why the sky is blue? answer in 20 words.")
        print(result.payload)




if __name__ == "__main__":
    unittest.main()