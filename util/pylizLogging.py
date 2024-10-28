

# log_config.py
from loguru import logger

# Disattiva tutti i log all'inizio
logger.remove()



def enable_logging(level="DEBUG", file_path=None, to_stdout=True):
    """Abilita il logging con il livello e il percorso file opzionali."""

    # Log su file
    if file_path:
        logger.add(
            file_path,
            level=level,
            format="{time} {level} {message}",
            rotation="10 MB",
            compression="zip",
            serialize=False
        )

    # Log su stdout
    if to_stdout:
        logger.add(
            lambda msg: print(msg, end=""),  # Stampare direttamente a stdout
            level=level,
            format="{time} {level} {message}"
        )

    logger.info("Logging abilitato per la libreria.")


def test_logging():
    logger.debug("This is a debug message")
    logger.info("This is an info message")
    logger.warning("This is a warning message")
    logger.error("This is an error message")
    logger.critical("This is a critical message")