
import unittest

from pylizlib.data.jsonUtils import JsonUtils


class TestJson(unittest.TestCase):

    def test_clean(self):
        json = "```json{'status': 'success', 'data': {'version': '0.0.1', 'execPath': '/usr/bin/eagle', 'prereleaseVersion': '0.0.1', 'buildVersion': '0.0.1', 'platform': 'linux'}}```"
        result = JsonUtils.clean_json(json)
        print(result)

if __name__ == '__main__':
    unittest.main()