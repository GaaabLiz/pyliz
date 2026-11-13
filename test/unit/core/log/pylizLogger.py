import unittest

from pylizlib.core.log.pylizLogger import PYLIZ_LIB_LOGGER_NAME, log_tests, logger


class PylizLoggerTestCase(unittest.TestCase):
    def test_logger_name(self):
        self.assertEqual(PYLIZ_LIB_LOGGER_NAME, "PylizLib")
        self.assertEqual(logger.name, PYLIZ_LIB_LOGGER_NAME)

    def test_log_tests_does_not_raise(self):
        log_tests()


if __name__ == "__main__":
    unittest.main()
