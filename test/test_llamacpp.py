import os
import unittest

import rich

from ai.llm.local.llamacpp import LlamaCpp
from ai.core.ai_power import AiPower
from ai.prompt.ai_prompts import prompt_llava_json
from util.pylizdir import PylizDir


def log(message: str):
    rich.print(message)


def progress(percent: int):
    rich.print(f"Progress: {percent}%")


class TestLlamaCPP(unittest.TestCase):

    def setUp(self):
        print("Setting up test...")
        self.dir = PylizDir(".pyliztest")
        self.ai_folder = self.dir.add_folder("ai", "ai")
        self.model_folder = self.dir.add_folder("models", "models")
        self.log_folder = self.dir.add_folder("log", "log")
        self.path_install = os.path.join(self.ai_folder, "llama.cpp")
        self.path_models = os.path.join(self.model_folder, "llama.cpp")
        self.path_logs = os.path.join(self.log_folder, "llama.cpp")
        self.obj = LlamaCpp(self.path_install, self.path_models, self.path_logs)

    def test_install_llava(self):
        try:
            self.obj.install_llava(AiPower.LOW, log, progress)
        except Exception as e:
            self.fail(e)

    def test_run_llava(self):
        try:
            result = self.obj.run_llava(AiPower.LOW, "/Users/gabliz/Pictures/obama343434333.jpg", prompt_llava_json)
            print(result)
        except Exception as e:
            self.fail(e)


if __name__ == "__main__":
    unittest.main()