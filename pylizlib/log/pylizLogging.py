

# log_config.py
from loguru import logger as base_logger

# Crea un logger specifico per A
logger = base_logger.bind(library="PylizLib")

# Disattiva tutti i log all'inizio
logger.remove()



def enable_logging(level="DEBUG", file_path=None, to_stdout=True):
    """Abilita il logging con il livello e il percorso file opzionali per A."""

    # Log su file
    if file_path:
        logger.add(
            file_path,
            level=level,
            format="{time} {level} {extra[library]} {message}",
            rotation="10 MB",
            compression="zip",
            serialize=False
        )

    # Log su stdout
    if to_stdout:
        logger.add(
            lambda msg: print(msg, end=""),  # Stampare direttamente a stdout
            level=level,
            format="{time:HH:mm:ss} {level} {extra[library]} {message}"
        )

    logger.info("Logging abilitato per la libreria PylizLib.")


def test_logging():
    logger.debug("This is a debug message from PylizLib")
    logger.info("This is an info message from PylizLib")
    logger.warning("This is a warning message from PylizLib")
    logger.error("This is an error message from PylizLib")
    logger.critical("This is a critical message from PylizLib")