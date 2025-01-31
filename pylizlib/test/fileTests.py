import os
import unittest

from loguru import logger

from pylizlib.data.jsonUtils import JsonUtils
from dotenv import load_dotenv

from pylizlib.log.pylizLogging import pyblizlib_log_test, LOGGER_PYLIZ_LIB_NAME
from pylizlib.os import fileutils


class TestFiles(unittest.TestCase):

    def test_clean_json(self):
        json = "```json{'status': 'success', 'data': {'version': '0.0.1', 'execPath': '/usr/bin/eagle', 'prereleaseVersion': '0.0.1', 'buildVersion': '0.0.1', 'platform': 'linux'}}```"
        result = JsonUtils.clean_json_apici(json)
        logger.enable(LOGGER_PYLIZ_LIB_NAME)
        pyblizlib_log_test()
        print(result)

    def test_file_hash(self):
        load_dotenv()
        path = os.getenv("LOCAL_IMAGE_FOR_TEST")
        print(path)
        print(fileutils.gen_file_hash(path))

if __name__ == '__main__':
    unittest.main()