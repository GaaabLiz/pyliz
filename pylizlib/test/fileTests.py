import logging
import os
import unittest
from pathlib import Path

from pylizlib.config.pylizapp import PylizApp
from pylizlib.data.jsonUtils import JsonUtils
from dotenv import load_dotenv

from pylizlib.log.pylizLogger import PYLIZ_LIB_LOGGER_NAME, logger
from pylizlib.os import fileutils, pathutils


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
        print(fileutils.gen_file_hash(path))

if __name__ == '__main__':
    unittest.main()