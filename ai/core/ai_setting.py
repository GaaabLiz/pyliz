from ai.core.ai_model_list import AiModelList
from ai.core.ai_models import AiModels
from ai.core.ai_power import AiPower
from ai.core.ai_source import AiSource
from ai.core.ai_source_type import AiSourceType
from ai.prompt.ai_prompts import AiPrompt


class AiQuery:
    def __init__(
            self,
            model: AiModelList,
            source_type: AiSourceType,
            power: AiPower,
            prompt: str,
            payload_file_path: str | None = None,
            remote_url: str | None = None,
            api_key: str | None = None,
    ):
        self.source: AiSource | None = None
        self.api_key = api_key
        self.model_name = model
        self.source_type = source_type
        self.remote_url = remote_url
        self.power = power
        self.prompt = prompt
        self.payload_file_path = payload_file_path

        self.check()
        self.setup()

    def setup(self):
        if self.model_name == AiModelList.LLAVA:
            self.source = AiModels.Llava.get_llava(self.power, self.source_type)
        if self.model_name == AiModelList.OPEN_MISTRAL:
            self.source = AiModels.Mistral.get_open_mistral()
        if self.model_name == AiModelList.PIXSTRAL:
            self.source = AiModels.Mistral.get_pixstral()
        if self.model_name == AiModelList.GEMINI:
            self.source = AiModels.Gemini.get_flash()
        else:
            raise ValueError("Model not found.")


    def check(self):
        if self.source_type == AiSourceType.OLLAMA_SERVER and self.remote_url is None:
            raise ValueError("Remote URL is required for Ollama Server.")
        if self.source_type == AiSourceType.LMSTUDIO_SERVER and self.remote_url is None:
            raise ValueError("Remote URL is required for LM Studio Server.")
        if self.source_type == AiSourceType.API_MISTRAL and self.api_key is None:
            raise ValueError("API Key is required for Mistral API.")
