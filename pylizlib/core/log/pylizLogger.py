"""Shared package logger configuration."""

import logging

PYLIZ_LIB_LOGGER_NAME = "PylizLib"
logger = logging.getLogger(PYLIZ_LIB_LOGGER_NAME)
logger.addHandler(logging.NullHandler())


def log_tests():
    """Emit one log entry for each standard log level."""

    logger.debug("Test logger debug message")
    logger.info("Test logger info message")
    logger.warning("Test logger warning message")
    logger.error("Test logger error message")
    logger.critical("Test logger critical message")