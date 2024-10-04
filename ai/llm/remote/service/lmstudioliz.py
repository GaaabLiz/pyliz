import json

from ai.llm.remote.data.lmstudioapi import LmmStudioApi
from ai.llm.remote.dto.lmstudio_models import LmStudioModelResult


class LmStudioLiz:

    def __init__(self, url: str):
        self.obj = LmmStudioApi(url)
        pass

    def get_loaded_models(self) -> LmStudioModelResult:
        call = self.obj.get_ram_loaded_models()
        if call.is_error():
            raise Exception(call.get_error())
        str_output = json.load(call.json)
        return LmStudioModelResult.from_dict(str_output)