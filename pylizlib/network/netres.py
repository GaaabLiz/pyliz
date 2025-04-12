from pylizlib.log.pylizLogger import logger
from requests import Response

from pylizlib.network.netrestype import NetResponseType


class NetResponse:

    def __init__(
            self,
            response: Response | None,
            response_type: NetResponseType,
            exception=None
    ):
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


    def __log(self):
        logger.trace(f"NetResponse: code={self.code} | type={self.type} | jsonHeader={self.has_json_header}")

    def __str__(self):
        return ""

    def is_successful(self):
        return self.code == 200

    def is_error(self):
        return self.code != 200

    def get_error(self):
        if self.hasResponse:
            return "(" + str(self.code) + "): " + self.response.text
        else:
            pre = "(" + self.type.value + ") "
            if self.exception is not None:
                pre = pre + str(self.exception)
            return pre
