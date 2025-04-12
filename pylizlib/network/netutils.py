import socket
from typing import Mapping

import requests
from pylizlib.log.pylizLogger import logger

from pylizlib.network.netres import NetResponse
from pylizlib.network.netrestype import NetResponseType


HEADER_ONLY_CONTENT_JSON = {"Content-Type": "application/json"}



def test_with_head(url: str) -> bool:
    try:
        response = requests.head(url, timeout=5)
        return response.status_code < 400
    except requests.RequestException as e:
        logger.error("Error while testing URL: " + url + " - " + str(e))
        return False


def is_internet_available() -> bool:
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
        sec_timeout: int | None = 10
) -> NetResponse:
    try:
        logger.trace("Executing GET request on URL: " + url)
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
    try:
        logger.trace("Executing POST request on URL: " + url)
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
    try:
        response = requests.head(url, timeout=5, allow_redirects=True)
        response.raise_for_status()
        file_size = response.headers.get('content-length', 0)
        if file_size is None:
            if exception_on_fail:
                raise ValueError("Unable to get file size for url: " + url)
            return -1
        return int(file_size)
    except requests.RequestException as e:
        if exception_on_fail:
            raise ValueError("Unable to get file size for url: " + url + ": " + str(e))
        return -1