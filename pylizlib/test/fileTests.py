import os
import unittest

from pylizlib.core.app.pylizapp import PylizApp
from dotenv import load_dotenv

from pylizlib.core.data.gen import gen_file_hash
from pylizlib.core.data.json import JsonUtils
from pylizlib.core.log.pylizLogger import logger


class TestFiles(unittest.TestCase):

    def setUp(self):
        pyliz_app = PylizApp("PylizTest", "0.0.1")
        logger.debug("setUp")

    def test_clean_json(self):
        json = "```json{'status': 'success', 'data': {'version': '0.0.1', 'execPath': '/usr/bin/eagle', 'prereleaseVersion': '0.0.1', 'buildVersion': '0.0.1', 'platform': 'linux'}}```"
        result = JsonUtils.clean_json_apici(json)
        print(result)

    def test_file_hash(self):
        load_dotenv()
        path = os.getenv("LOCAL_IMAGE_FOR_TEST")
        print(path)
        print(gen_file_hash(path))

if __name__ == '__main__':
    unittest.main()