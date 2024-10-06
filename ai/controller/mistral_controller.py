from ai.core.ai_setting import AiSettings


class MistralController:

    def __init__(self, ai_settings: AiSettings, api_key: str):
        self.ai_settings = ai_settings
        self.api_key = api_key

    def run_pixstral_vision(self, image_path: str) -> str:
        raise NotImplementedError("This method is not implemented.")

