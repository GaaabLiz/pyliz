import unittest

from pylizlib.core.temp.pylizscript import PylizScript
from pylizlib.core.os import ActionTest, ActionExecCli


class TestScripts(unittest.TestCase):


    def test1(self):
        script = PylizScript("test1")
        a1 = ActionExecCli("C:\\", ["echo", "Hello World"], "C:\\test")
        script.add_command(ActionTest("parametro 1"))
        script.add_command(ActionTest("parametro 2"))
        script.add_command(a1)
        script.run_all()


if __name__ == "__main__":
    unittest.main()