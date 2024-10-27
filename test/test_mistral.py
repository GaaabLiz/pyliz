
import os
import unittest

from numba.cuda.printimpl import print_item

from ai.controller.ai_runner import AiRunner
from ai.controller.mistral_controller import MistralController
from ai.core.ai_inputs import AiInputs
from ai.core.ai_model_list import AiModelList
from ai.core.ai_power import AiPower
from ai.core.ai_prompts import AiPrompt
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
            power=AiPower.LOW,
            api_key=os.getenv('MISTRAL_API_KEY'),
        )
        inputs = AiInputs(prompt="Why is the sky blue? answer in 20 words or less")
        result = AiRunner(setting, inputs).run()
        print(result.payload)


    def test2(self):
        setting = AiSettings(
            model=AiModelList.PIXSTRAL,
            source_type=AiSourceType.API_MISTRAL,
            power=AiPower.MEDIUM,
            api_key=os.getenv('MISTRAL_API_KEY'),
        )
        inputs = AiInputs(prompt=AiPrompt.LLAVA_DETAILED.value, file_path=os.getenv('LOCAL_IMAGE_FOR_TEST'))
        result = AiRunner(setting, inputs).run()
        print("Local image for test: ", os.getenv('LOCAL_IMAGE_FOR_TEST'))
        print(f"Result status: {result.status}")
        print("Result error: ", result.error)
        print("Result payload: ", result.payload)




if __name__ == "__main__":
    unittest.main()