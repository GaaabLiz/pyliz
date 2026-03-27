import unittest
from unittest.mock import patch

from pylizlib.core.network.ssl import ignore_context_ssl


class SslHelpersTestCase(unittest.TestCase):

    @patch("pylizlib.core.network.ssl.urllib3.disable_warnings")
    @patch("pylizlib.core.network.ssl.ssl.create_default_context")
    def test_ignore_context_ssl(self, mock_context_factory, mock_disable_warnings):
        context = mock_context_factory.return_value

        ignore_context_ssl()

        self.assertIs(context.check_hostname, False)
        self.assertIsNotNone(context.verify_mode)
        mock_disable_warnings.assert_called_once()


if __name__ == "__main__":
    unittest.main()