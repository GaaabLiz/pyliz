import json
from typing import Callable

from api.data.ollamapi import OllamaApiLegacy, Ollamapi
from ollama import Client

from api.dto.ollama_models import OllamaModels


class OllamalizLegacy:

    def __init__(self):
        pass

    @staticmethod
    def check_ollama(url: str):
        response = OllamaApiLegacy.check_ollama_status(url)
        if response.is_successful():
            return
        else:
            error = response.get_error()
            raise Exception(error)


class Ollamaliz:

    def __init__(self, url: str):
        self.obj = Ollamapi(url)
        pass

    def get_models_list(self) -> OllamaModels:
        response = self.obj.get_models_list()
        data = json.loads(response)
        return OllamaModels.from_json(data)

    def has_model(self, name: str):
        models = self.get_models_list().models
        for model in models:
            if model.name == name:
                return True
        return False

    def download_model(self, name: str, en_stream: bool, callback: Callable[[str], None] | None = None):
        return self.obj.download_model(name, en_stream, callback)



