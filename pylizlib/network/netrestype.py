from enum import Enum


class NetResponseType(Enum):
    OK200 = "ok200"
    ERROR = "error"
    CONNECTION_ERROR = "connection_error"
    TIMEOUT = "timeout"
    REQUEST_ERROR = "request_error"

