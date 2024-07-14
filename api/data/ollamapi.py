import json
from typing import Callable

import ollama
from ollama import Client

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
        self.client = ollama.client = Client(host=url)

    def get_models_list(self):
        mappings = self.client.list()
        json_str = json.dumps(mappings)
        return json_str

    def download_model(self, name: str, en_stream: bool, callback: Callable[[str], None] | None = None):
        stream = self.client.pull(
            model='name',
            stream=en_stream,
        )
        if en_stream:
            for data in stream:
                if callback:
                    callback(data["status"])
