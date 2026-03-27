"""SSL utility helpers for network operations."""

import ssl

import urllib3


def ignore_context_ssl():
    """Disable SSL certificate checks and warnings for urllib3.

    This helper should only be used in controlled environments.
    """

    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


