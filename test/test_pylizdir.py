
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

from util.cfgutils import CfgItem
from util.pylizdir import PylizDir

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


class TestPylizDir(unittest.TestCase):

    def setUp(self):
        list = [
            CfgItem("api_keys", "mistral", "cringewhoreads"),
            CfgItem("api_keys", "openai", "cringewhoreads"),
            CfgItem("general", "test", "valueFromGeneral"),
        ]
        PylizDir.create(".testPylizdir", list)
        print("SDone setup")


    def test1(self):
        print(PylizDir.get_models_folder())
        print(PylizDir.get_ai_folder())
        print(PylizDir.get_logs_path())
        print(PylizDir.get_ini_item("api_keys", "mistral"))
        print(PylizDir.get_ini_item("general", "test"))




if __name__ == "__main__":
    unittest.main()