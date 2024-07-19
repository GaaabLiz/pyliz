import os
import unittest

import rich

from ai.llm.llamacpp import LlamaCpp
from ai.model.ai_power import AiPower
from util.pylizdir import PylizDir


def log(message: str):
    rich.print(message)


def progress(percent: int):
    rich.print(f"Progress: {percent}%")


class TestLlamaCPP(unittest.TestCase):

    def setUp(self):
        PylizDir.create()
        PylizDir.set_default()
        self.install_path = os.path.join(PylizDir.get_ai_folder(), "llama.cpp")
        self.obj = LlamaCpp(self.install_path, PylizDir.get_models_folder())

    def test_clone_and_build(self):
        try:
            self.obj.clone_and_build(log)
        except Exception as e:
            self.fail(e)

    def test_install_llava(self):
        try:
            self.obj.install_llava(AiPower.LOW, log, progress)
        except Exception as e:
            self.fail(e)


if __name__ == "__main__":
    unittest.main()