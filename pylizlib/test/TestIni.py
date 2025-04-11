import unittest

from pylizlib.config.pylizapp import PylizApp


class TestScripts(unittest.TestCase):

    def setUp(self):
        self.dir = PylizApp(".pyliz")

    def test1(self):
        self.dir.create_ini("test.ini", [])
        self.dir.set_ini_value("sezione1", "chiave1", "value1")
        self.dir.set_ini_value("sezione1", "chiave1", False)


if __name__ == "__main__":
    unittest.main()