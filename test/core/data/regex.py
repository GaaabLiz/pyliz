import unittest

import typer

from pylizlib.core.data.regex import is_valid_url, validate_url


class RegexHelpersTestCase(unittest.TestCase):
    def test_is_valid_url_accepts_https(self):
        self.assertTrue(is_valid_url("https://example.com/path?q=1"))

    def test_is_valid_url_accepts_localhost(self):
        self.assertTrue(is_valid_url("http://localhost:8080"))

    def test_is_valid_url_rejects_plain_text(self):
        self.assertFalse(is_valid_url("not-a-url"))

    def test_is_valid_url_rejects_missing_scheme(self):
        self.assertFalse(is_valid_url("example.com/path"))

    def test_validate_url_returns_input_when_valid(self):
        url = "https://example.com/resource"
        self.assertEqual(validate_url(url), url)

    def test_validate_url_raises_for_invalid_url(self):
        with self.assertRaises(typer.BadParameter):
            validate_url("invalid-url")

    def test_validate_url_custom_message(self):
        with self.assertRaisesRegex(typer.BadParameter, "URL custom error"):
            validate_url("invalid-url", "URL custom error")


if __name__ == "__main__":
    unittest.main()
