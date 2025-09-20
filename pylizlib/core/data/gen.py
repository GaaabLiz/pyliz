import hashlib
import random
import string
from datetime import datetime


def gen_random_string(length: int) -> str:
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for _ in range(length))


def gen_timestamp_log_name(prefix: str, extension: str):
    return prefix + datetime.now().strftime("%Y%m%d_%H%M%S") + extension

def gen_file_hash(path):
    sha256_hash = hashlib.sha256()
    # Leggi il file a blocchi per evitare problemi con file di grandi dimensioni
    with open(path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()
