from network.netres import NetResponse
from network.netutils import exec_get, exec_post

OLLAMA_PORT = "11434"
OLLAMA_HTTP_LOCALHOST_URL = "http://localhost:" + OLLAMA_PORT

# https://github.com/ollama/ollama-python
# https://github.com/ollama/ollama/blob/main/docs/api.md

class OllamaApiLegacy:
    def __init__(self):
        pass

    @staticmethod
    def check_ollama_status(url) -> NetResponse:
        return exec_get(url)

    @staticmethod
    def get_installed_models(url) -> NetResponse:
        api_url = url + "/api/tags"
        return exec_get(api_url)

    @staticmethod
    def send_query(
            url: str,
            prompt: str,
            model_name: str,
    ) -> NetResponse:
        api_url = url + "/api/generate"
        payload = {
            "model": model_name,
            "prompt": prompt,
            "stream": False
        }
        return exec_post(api_url, payload, False)

    @staticmethod
    def send_llava_query(
            url: str,
            prompt: str,
            image_base_64: str,
            model_name: str,
    ) -> NetResponse:
        api_url = url + "/api/generate"
        payload = {
            "model": model_name,
            "prompt": prompt,
            "images": [image_base_64],
            "format": "json",
            "stream": False
        }
        return exec_post(api_url, payload, False)


class Ollamapi:

    def __init__(self, url: str):
        self.url = url
        pass
