import os.path
import sys

from loguru import logger

from pylizlib.os import pathutils

LOGGER_PYLIZ_LIB_NAME = "PylizLib"

path_log = os.path.join(pathutils.get_app_home_dir(".pyliz"), "logs")
pathutils.check_path(path_log, True)
path_log_file = os.path.join(path_log, "pylizlib.log")

config = {
    "handlers": [
        {"sink": sys.stdout, "format": "{time:HH:mm:ss} [{level}]: {message}", "level": "TRACE"},
        {"sink": path_log_file, "serialize": True, "level": "TRACE"},
    ]
}

logger.configure(**config)
logger.disable(LOGGER_PYLIZ_LIB_NAME)


def pyblizlib_log_test():
    logger.info("This is a test log message from PylizLib.")
    logger.debug("This is a debug message from PylizLib.")
    logger.error("This is an error message from PylizLib.")
    logger.warning("This is a warning message from PylizLib.")
    logger.critical("This is a critical message from PylizLib.")
    logger.trace("This is a trace message from PylizLib.")


# # Crea un logger specifico per PylizLib
# logger = base_logger.bind(library="PylizLib")
#
# # Mantieni una lista di ID delle destinazioni per rimuoverle
# _destinations = []
#
# # Disattiva tutti i log globali all'inizio
# base_logger.remove()
#
# def enable_logging(level="DEBUG", file_path=None, to_stdout=True):
#     """Abilita il logging con il livello e il percorso file opzionali per PylizLib."""
#
#     global _destinations
#
#     # Rimuovi eventuali destinazioni già aggiunte
#     for dest in _destinations:
#         logger.remove(dest)
#     _destinations = []
#
#     # Log su file
#     if file_path:
#         dest_file = logger.add(
#             file_path,
#             level=level,
#             format="{time} {level} {extra[library]} {message}",
#             rotation="10 MB",
#             compression="zip",
#             serialize=False
#         )
#         _destinations.append(dest_file)
#
#     # Log su stdout
#     if to_stdout:
#         dest_stdout = logger.add(
#             lambda msg: print(msg, end=""),  # Stampare direttamente a stdout
#             level=level,
#             format="{time:HH:mm:ss} {level} {extra[library]} {message}"
#         )
#         _destinations.append(dest_stdout)
#
#     logger.info("Logging abilitato per la libreria PylizLib.")