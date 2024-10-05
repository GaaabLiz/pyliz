import json

from ai.llm.remote.data.lmstudioapi import LmmStudioApi
from ai.llm.remote.dto.lmstudio_models import LmStudioModelList


class LmStudioLiz:

    def __init__(self, url: str):
        self.obj = LmmStudioApi(url)
        pass

    def get_loaded_models(self) -> LmStudioModelList:
        call = self.obj.get_ram_loaded_models()
        if call.is_error():
            raise Exception(call.get_error())
        return LmStudioModelList.from_json(call.response.text)

    def has_model_loaded(self, model_id: str) -> bool:
        models = self.get_loaded_models()
        for model in models.data:
            if model.id == model_id:
                return True
        return False

    def send_vision_prompt(self, image_base_64: str, prompt: str) -> str:
        raise NotImplementedError("Not implemented yet.")
