from network.netres import NetResponse
from network.netutils import exec_get

LMSTUDIO_PORT = "1234"
LMSTUDIO_HTTP_LOCALHOST_URL = "http://localhost:" + LMSTUDIO_PORT


class LmmStudioApi:

    def __init__(self, url: str):
        self.url = url

    def get_ram_loaded_models(self) -> NetResponse:
        api_url = self.url + "/v1/models"
        return exec_get(api_url)
