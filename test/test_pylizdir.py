import unittest

import sys
import os

from util.cfgutils import CfgItem
from util.pylizdir import PylizDir

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


class TestPylizDir(unittest.TestCase):

    liz = PylizDir(".testPylizdir")

    def setUp(self):
        list = [
            CfgItem("api_keys", "mistral", "cringewhoreads"),
            CfgItem("api_keys", "openai", "cringewhoreads"),
            CfgItem("general", "test", "valueFromGeneral2"),
        ]
        self.liz.create_ini("testFromPython.ini", list)
        print("SDone setup")

    def print_values(self):
        print(self.liz.get_ini_value("api_keys", "mistral"))
        print(self.liz.get_ini_value("api_keys", "openai"))
        print(self.liz.get_ini_value("general", "test"))

    def testGet(self):
        self.print_values()

    def testSet(self):
        self.print_values()
        self.liz.set_ini_value("api_keys", "mistral", "newMistralKey")
        self.print_values()




if __name__ == "__main__":
    unittest.main()