# pylizlib/log.py
from loguru import logger as base_logger

# Crea un logger specifico per PylizLib
logger = base_logger.bind(library="PylizLib")

# Mantieni una lista di ID delle destinazioni per rimuoverle
_destinations = []

# Disattiva tutti i log globali all'inizio
base_logger.remove()

def enable_logging(level="DEBUG", file_path=None, to_stdout=True):
    """Abilita il logging con il livello e il percorso file opzionali per PylizLib."""

    global _destinations

    # Rimuovi eventuali destinazioni già aggiunte
    for dest in _destinations:
        logger.remove(dest)
    _destinations = []

    # Log su file
    if file_path:
        dest_file = logger.add(
            file_path,
            level=level,
            format="{time} {level} {extra[library]} {message}",
            rotation="10 MB",
            compression="zip",
            serialize=False
        )
        _destinations.append(dest_file)

    # Log su stdout
    if to_stdout:
        dest_stdout = logger.add(
            lambda msg: print(msg, end=""),  # Stampare direttamente a stdout
            level=level,
            format="{time:HH:mm:ss} {level} {extra[library]} {message}"
        )
        _destinations.append(dest_stdout)

    logger.info("Logging abilitato per la libreria PylizLib.")