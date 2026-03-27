"""Regular-expression and URL validation helpers."""

import re
from urllib.parse import urlparse

import typer


def is_valid_url(url: str) -> bool:
    """Return ``True`` if the input string matches a URL pattern."""

    regex = re.compile(
        r'^(?:http|ftp)s?://'
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|'
        r'localhost|'
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}|'
        r'\[?[A-F0-9]*:[A-F0-9:]+\]?)'
        r'(?::\d+)?'
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)

    return re.match(regex, url) is not None


def validate_url(url: str, error_msg: str = "The URL is not valid.") -> str:
    """Validate a URL for CLI arguments and raise ``typer.BadParameter`` on failure."""

    result = urlparse(url)
    if not (result.scheme and result.netloc):
        raise typer.BadParameter(error_msg)
    return url
