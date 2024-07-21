import os
import unittest

import rich

from ai.llm.local.llamacpp import LlamaCpp
from ai.core.ai_power import AiPower
from ai.core.ai_prompts import prompt_llava_1
from util.pylizdir import PylizDir


def log(message: str):
    rich.print(message)


def progress(percent: int):
    rich.print(f"Progress: {percent}%")


class TestLlamaCPP(unittest.TestCase):

    def setUp(self):
        print("Setting up test...")
        PylizDir.create()
        path_install: str = os.path.join(PylizDir.get_ai_folder(), "llama.cpp")
        path_models: str = PylizDir.get_models_folder()
        path_logs: str = os.path.join(PylizDir.get_logs_path(), "llama.cpp")
        self.obj = LlamaCpp(path_install, path_models, path_logs)

    def test_install_llava(self):
        try:
            self.obj.install_llava(AiPower.LOW, log, progress)
        except Exception as e:
            self.fail(e)

    def test_run_llava(self):
        try:
            result = self.obj.run_llava(AiPower.LOW, "/Users/gabliz/Pictures/obama343434333.jpg", prompt_llava_1)
            print(result)
        except Exception as e:
            self.fail(e)


if __name__ == "__main__":
    unittest.main()