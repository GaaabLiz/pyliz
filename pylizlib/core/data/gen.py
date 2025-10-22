import hashlib
import random
import string
from datetime import datetime


def gen_random_string(length: int) -> str:
    """
    Generate a random string of fixed length.
    :param length: Length of the generated string
    :return: Random string
    """
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for _ in range(length))


def gen_timestamp_log_name(prefix: str, extension: str):
    """
    Generate a log file name with a timestamp.
    :param prefix: Prefix for the log file name
    :param extension: Extension for the log file name
    :return: Log file name with timestamp
    """
    return prefix + datetime.now().strftime("%Y%m%d_%H%M%S") + extension

def gen_file_hash(path):
    """
    Generate SHA-256 hash of a file.
    :param path: Path to the file
    :return: SHA-256 hash of the file
    """
    sha256_hash = hashlib.sha256()
    # Leggi il file a blocchi per evitare problemi con file di grandi dimensioni
    with open(path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()
