
import os
import unittest

from ai.llm.local.llamacpplib import LlamaCppLib
from util.pylizdir import PylizDir


class TestLlamaCPPLib(unittest.TestCase):

    def setUp(self):
        print("Setting up test...")



    def test1(self):
        dir = PylizDir(".medializ")
        LlamaCppLib.run_llama3("What is SpaceX ?", dir.get_path())


if __name__ == "__main__":
    unittest.main()