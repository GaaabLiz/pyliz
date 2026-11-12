"""Shared package logger configuration."""

import logging

TRACE_LEVEL_NUM = 5
logging.addLevelName(TRACE_LEVEL_NUM, "TRACE")


def _trace(self, message, *args, **kws):
    if self.isEnabledFor(TRACE_LEVEL_NUM):
        self._log(TRACE_LEVEL_NUM, message, args, **kws)


if not hasattr(logging.Logger, "trace"):
    logging.Logger.trace = _trace

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
