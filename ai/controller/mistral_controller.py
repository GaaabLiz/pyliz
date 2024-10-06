from ai.core.ai_setting import AiSettings
from ai.llm.remote.service.mistraliz import Mistraliz
from model.operation import Operation


class MistralController:

    def __init__(self, ai_settings: AiSettings, api_key: str):
        self.ai_settings = ai_settings
        self.api_key = api_key
        self.mistraliz = Mistraliz(api_key)

    def run_pixstral_vision(self, image_path: str, prompt: str) -> Operation[str]:
        try:
            model_name = self.ai_settings.source.mistral_name
            result = self.mistraliz.run_pixstral_vision(model_name, image_path, prompt)
            return Operation(status=True, payload=result)
        except Exception as e:
            return Operation(status=False, error=str(e))

    def run_open_mistral(self, prompt: str) -> Operation[str]:
        try:
            model_name = self.ai_settings.source.mistral_name
            result = self.mistraliz.run_open_mistral(model_name, prompt)
            return Operation(status=True, payload=result)
        except Exception as e:
            return Operation(status=False, error=str(e))

