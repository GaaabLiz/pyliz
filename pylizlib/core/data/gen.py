"""General-purpose value and file generation helpers."""

import hashlib
import random
import string
from datetime import datetime
from os import PathLike


def gen_random_string(length: int) -> str:
    """Generate a random alphanumeric string.

    :param length: Number of characters in the returned string.
    :return: Random string containing letters and digits.
    """

    characters = string.ascii_letters + string.digits
    return "".join(random.choice(characters) for _ in range(length))


def gen_timestamp_log_name(prefix: str, extension: str) -> str:
    """Generate a log-like file name with a timestamp.

    :param prefix: Prefix for the generated name.
    :param extension: File extension, for example ``.log``.
    :return: String in the form ``{prefix}{YYYYMMDD_HHMMSS}{extension}``.
    """

    return prefix + datetime.now().strftime("%Y%m%d_%H%M%S") + extension


def gen_file_hash(path: str | PathLike[str]) -> str:
    """Generate the SHA-256 hash for a file.

    :param path: Path to the input file.
    :return: Hex digest string.
    """

    sha256_hash = hashlib.sha256()
    with open(path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()
