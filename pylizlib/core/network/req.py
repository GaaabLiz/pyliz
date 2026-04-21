"""HTTP/network request helpers and response wrappers."""

import socket
from enum import Enum
from typing import Mapping

import requests
from requests.models import Response

from pylizlib.core.log.pylizLogger import logger


class NetResponseType(Enum):
    """Result classification for network requests."""

    OK200 = "ok200"
    ERROR = "error"
    CONNECTION_ERROR = "connection_error"
    TIMEOUT = "timeout"
    REQUEST_ERROR = "request_error"


class NetResponse:
    """Standard wrapper around ``requests`` responses and request errors."""

    def __init__(
        self,
        response: Response | None,
        response_type: NetResponseType,
        exception=None,
    ):
        """Initialize a response wrapper and derive helper fields."""

        self.has_json_header = None
        self.json = None
        self.response = response
        self.hasResponse = self.response is not None
        if self.hasResponse:
            self.code = self.response.status_code
            self.text: str = self.response.text
        else:
            self.code = None
        self.type = response_type
        self.exception = exception
        if self.hasResponse:
            self.has_json_header = "application/json" in self.response.headers.get("Content-Type", "")
            if self.has_json_header:
                self.json = self.response.json()
        self.__log()

    def __log(self) -> None:
        """Emit internal diagnostic log for the response wrapper."""

        log_trace = getattr(logger, "trace", logger.debug)
        log_trace(f"NetResponse: code={self.code} | type={self.type} | jsonHeader={self.has_json_header}")

    def __str__(self) -> str:
        """Return a readable summary of the response state."""

        return f"NetResponse(code={self.code}, type={self.type.value})"

    def is_successful(self) -> bool:
        """Return ``True`` if HTTP status code is 200."""

        return self.code == 200

    def is_error(self) -> bool:
        """Return ``True`` if HTTP status code is not 200."""

        return self.code != 200

    def get_error(self) -> str:
        """Return a human-readable error description."""

        if self.hasResponse:
            return "(" + str(self.code) + "): " + self.response.text
        else:
            pre = "(" + self.type.value + ") "
            if self.exception is not None:
                pre = pre + str(self.exception)
            return pre


HEADER_ONLY_CONTENT_JSON = {"Content-Type": "application/json"}


def test_with_head(url: str) -> bool:
    """Return ``True`` when a HEAD request gets a non-error status code."""

    try:
        response = requests.head(url, timeout=5)
        return response.status_code < 400
    except requests.RequestException as e:
        logger.error("Error while testing URL: " + url + " - " + str(e))
        return False


def is_endpoint_reachable(url: str) -> bool:
    """Return ``True`` when a GET request responds with HTTP 200."""

    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            return True
        else:
            return False
    except requests.RequestException as e:
        logger.error("Error while testing URL: " + url + " - " + str(e))
        return False


def is_internet_available() -> bool:
    """Check internet connectivity by opening a socket to a public DNS host."""

    host = "8.8.8.8"
    port = 53
    timeout = 3
    try:
        socket.setdefaulttimeout(timeout)
        # Utilizza un blocco `with` per gestire automaticamente il socket
        with socket.create_connection((host, port)):
            return True
    except OSError:
        return False


def exec_get(
    url: str,
    headers: Mapping[str, str | bytes | None] | None = None,
    sec_timeout: int | None = 10,
) -> NetResponse:
    """Execute an HTTP GET request and return a standardized ``NetResponse``."""

    try:
        getattr(logger, "trace", logger.debug)("Executing GET request on URL: " + url)
        response = requests.get(url, allow_redirects=True, headers=headers, timeout=sec_timeout)
        if response.status_code == 200:
            return NetResponse(response, NetResponseType.OK200)
        else:
            return NetResponse(response, NetResponseType.ERROR)
    except requests.ConnectionError as e:
        return NetResponse(None, NetResponseType.CONNECTION_ERROR, e)
    except requests.Timeout as e:
        return NetResponse(None, NetResponseType.TIMEOUT, e)
    except requests.RequestException as e:
        return NetResponse(None, NetResponseType.REQUEST_ERROR, e)


def exec_post(
    url: str,
    payload,
    headers: Mapping[str, str | bytes | None] | None = None,
    verify_bool: bool = False,
) -> NetResponse:
    """Execute an HTTP POST request and return a standardized ``NetResponse``."""

    try:
        getattr(logger, "trace", logger.debug)("Executing POST request on URL: " + url)
        response = requests.post(url, json=payload, verify=verify_bool, allow_redirects=True, headers=headers)
        if response.status_code == 200:
            return NetResponse(response, NetResponseType.OK200)
        else:
            return NetResponse(response, NetResponseType.ERROR)
    except requests.ConnectionError as e:
        return NetResponse(None, NetResponseType.CONNECTION_ERROR, e)
    except requests.Timeout as e:
        return NetResponse(None, NetResponseType.TIMEOUT, e)
    except requests.RequestException as e:
        return NetResponse(None, NetResponseType.REQUEST_ERROR, e)


def get_file_size_byte(url: str, exception_on_fail: bool = False) -> int:
    """Return file size in bytes from the ``content-length`` header.

    :param url: Remote file URL.
    :param exception_on_fail: Raise ``ValueError`` instead of returning ``-1`` when failing.
    :return: File size in bytes, or ``-1`` on failure when ``exception_on_fail`` is ``False``.
    """

    try:
        response = requests.head(url, timeout=5, allow_redirects=True)
        response.raise_for_status()
        file_size = response.headers.get("content-length", 0)
        if file_size is None:
            if exception_on_fail:
                raise ValueError("Unable to get file size for url: " + url)
            return -1
        return int(file_size)
    except requests.RequestException as e:
        if exception_on_fail:
            raise ValueError("Unable to get file size for url: " + url + ": " + str(e))
        return -1
