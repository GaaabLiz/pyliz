
import os
import unittest

from ai.llm.remote.service.lmstudioliz import LmStudioLiz
import sys
import os
from dotenv import load_dotenv
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


class TestLmStudio(unittest.TestCase):

    def setUp(self):
        load_dotenv()
        print("Setting up test...")


    def test1(self):
        liz = LmStudioLiz(os.getenv('LMSTUDIO_URL'))
        obj = liz.get_loaded_models()
        print(obj.data)

    def test2(self):
        import http.client
        conn = http.client.HTTPConnection("192.168.0.253", 1234)
        conn.request("GET", "/v1/models")
        response = conn.getresponse()

        print(response.status, response.reason)
        data = response.read()
        print(data)



if __name__ == "__main__":
    unittest.main()