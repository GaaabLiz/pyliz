from ai.core.ai_model_list import AiModelList
from ai.core.ai_setting import AiSetting, AiQuery
from ai.llm.remote.service.mistraliz import Mistraliz
from model.operation import Operation


class MistralController:

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.mistraliz = Mistraliz(api_key)

    def run(
            self,
            query: AiQuery,
    ) -> Operation[str]:
        if query.setting.model == AiModelList.OPEN_MISTRAL:
            return self.__run_open_mistral(query.setting.source.model_name, query.prompt)
        if query.setting.model == AiModelList.PIXSTRAL:
            return self.__run_pixstral_vision(query.setting.source.model_name, query.prompt, query.payload_path)
        raise NotImplementedError("Model not implemented in MistralController")

    def __run_pixstral_vision(self, model_id: str, prompt: str, image_path: str | None) -> Operation[str]:
        try:
            if image_path is None:
                raise ValueError("Image path is required for Pixstral Vision")
            result = self.mistraliz.run_pixstral_vision(model_id, image_path, prompt)
            return Operation(status=True, payload=result)
        except Exception as e:
            return Operation(status=False, error=str(e))

    def __run_open_mistral(self, model_id: str, prompt: str) -> Operation[str]:
        try:
            result = self.mistraliz.run_open_mistral(model_id, prompt)
            return Operation(status=True, payload=result)
        except Exception as e:
            return Operation(status=False, error=str(e))

