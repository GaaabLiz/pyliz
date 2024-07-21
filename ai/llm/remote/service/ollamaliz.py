import json
from typing import Callable

from ai.llm.remote.data.ollamapi import OllamaApiLegacy, Ollamapi

from ai.llm.remote.dto.ollama_models import OllamaModels
from ai.llm.remote.dto.ollama_response import OllamaResponse
from model.operation import Operation


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

    def llava_query(
            self,
            prompt: str,
            image_base_64: str,
            model_name: str,
    ) -> Operation[OllamaResponse]:
        response = OllamaApiLegacy.send_llava_query(self.obj.url, prompt, image_base_64, model_name)
        if response.is_successful():
            resp_text = response.text
            resp_text_json = json.loads(resp_text)
            resp_obj = OllamaResponse.from_json(resp_text_json)
            return Operation(payload=resp_obj, status=True)
        else:
            error = response.get_error()
            return Operation(status=False, error=error)





