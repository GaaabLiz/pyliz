import unittest
from unittest.mock import MagicMock, patch

import requests

from pylizlib.core.network.req import (
    NetResponse,
    NetResponseType,
    exec_get,
    exec_post,
    get_file_size_byte,
    is_endpoint_reachable,
    is_internet_available,
)
from pylizlib.core.network.req import (
    test_with_head as _test_with_head,
)


class NetResponseTestCase(unittest.TestCase):

    def test_netresponse_with_json_header(self):
        response = MagicMock()
        response.status_code = 200
        response.text = "ok"
        response.headers = {"Content-Type": "application/json"}
        response.json.return_value = {"ok": True}

        wrapped = NetResponse(response, NetResponseType.OK200)

        self.assertTrue(wrapped.hasResponse)
        self.assertTrue(wrapped.has_json_header)
        self.assertEqual(wrapped.json, {"ok": True})
        self.assertTrue(wrapped.is_successful())
        self.assertFalse(wrapped.is_error())

    def test_netresponse_without_response(self):
        wrapped = NetResponse(None, NetResponseType.TIMEOUT, exception=TimeoutError("timeout"))

        self.assertFalse(wrapped.hasResponse)
        self.assertIn("timeout", wrapped.get_error())


class RequestHelpersTestCase(unittest.TestCase):

    @patch("pylizlib.core.network.req.requests.head")
    def test_test_with_head_true(self, mock_head):
        mock_head.return_value.status_code = 200
        self.assertTrue(_test_with_head("https://example.com"))

    @patch("pylizlib.core.network.req.requests.head", side_effect=requests.RequestException("bad"))
    def test_test_with_head_false_on_exception(self, _):
        self.assertFalse(_test_with_head("https://example.com"))

    @patch("pylizlib.core.network.req.requests.get")
    def test_is_endpoint_reachable(self, mock_get):
        mock_get.return_value.status_code = 200
        self.assertTrue(is_endpoint_reachable("https://example.com"))
        mock_get.return_value.status_code = 500
        self.assertFalse(is_endpoint_reachable("https://example.com"))

    @patch("pylizlib.core.network.req.socket.create_connection")
    def test_is_internet_available_true(self, mock_create_connection):
        mock_context = MagicMock()
        mock_create_connection.return_value.__enter__.return_value = mock_context
        self.assertTrue(is_internet_available())

    @patch("pylizlib.core.network.req.socket.create_connection", side_effect=OSError())
    def test_is_internet_available_false(self, _):
        self.assertFalse(is_internet_available())

    @patch("pylizlib.core.network.req.requests.get")
    def test_exec_get_ok_and_error(self, mock_get):
        response = MagicMock()
        response.status_code = 200
        response.text = "ok"
        response.headers = {}
        mock_get.return_value = response

        result = exec_get("https://example.com")
        self.assertEqual(result.type, NetResponseType.OK200)

        response.status_code = 404
        result = exec_get("https://example.com")
        self.assertEqual(result.type, NetResponseType.ERROR)

    @patch("pylizlib.core.network.req.requests.get", side_effect=requests.ConnectionError("offline"))
    def test_exec_get_connection_error(self, _):
        result = exec_get("https://example.com")
        self.assertEqual(result.type, NetResponseType.CONNECTION_ERROR)

    @patch("pylizlib.core.network.req.requests.post")
    def test_exec_post_ok_and_error(self, mock_post):
        response = MagicMock()
        response.status_code = 200
        response.text = "ok"
        response.headers = {}
        mock_post.return_value = response
        result = exec_post("https://example.com", payload={"x": 1})
        self.assertEqual(result.type, NetResponseType.OK200)

        response.status_code = 400
        result = exec_post("https://example.com", payload={"x": 1})
        self.assertEqual(result.type, NetResponseType.ERROR)

    @patch("pylizlib.core.network.req.requests.post", side_effect=requests.Timeout("timeout"))
    def test_exec_post_timeout(self, _):
        result = exec_post("https://example.com", payload={})
        self.assertEqual(result.type, NetResponseType.TIMEOUT)

    @patch("pylizlib.core.network.req.requests.head")
    def test_get_file_size_byte_success(self, mock_head):
        response = MagicMock()
        response.headers = {"content-length": "42"}
        response.raise_for_status.return_value = None
        mock_head.return_value = response

        self.assertEqual(get_file_size_byte("https://example.com/file.bin"), 42)

    @patch("pylizlib.core.network.req.requests.head")
    def test_get_file_size_byte_missing_header_defaults_zero(self, mock_head):
        response = MagicMock()
        response.headers = {}
        response.raise_for_status.return_value = None
        mock_head.return_value = response

        self.assertEqual(get_file_size_byte("https://example.com/file.bin"), 0)

    @patch("pylizlib.core.network.req.requests.head", side_effect=requests.RequestException("bad"))
    def test_get_file_size_byte_fail_modes(self, _):
        self.assertEqual(get_file_size_byte("https://example.com/file.bin"), -1)
        with self.assertRaises(ValueError):
            get_file_size_byte("https://example.com/file.bin", exception_on_fail=True)


if __name__ == "__main__":
    unittest.main()