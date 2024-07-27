
import os
import unittest

import rich

from ai.llm.local.llamacpp import LlamaCpp
from ai.core.ai_power import AiPower
from ai.core.ai_prompts import prompt_llava_1
from ai.llm.local.llamacpplib import LlamaCppLib
from util.pylizdir import PylizDir




class TestLlamaCPPLib(unittest.TestCase):

    def setUp(self):
        print("Setting up test...")
        PylizDir.create()
        path_install: str = os.path.join(PylizDir.get_ai_folder(), "llama.cpp")
        path_models: str = PylizDir.get_models_folder()
        path_logs: str = os.path.join(PylizDir.get_logs_path(), "llama.cpp")


    def test1(self):
        LlamaCppLib.run_llama3("What is SpaceX ?")


if __name__ == "__main__":
    unittest.main()