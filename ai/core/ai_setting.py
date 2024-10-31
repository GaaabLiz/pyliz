from dataclasses import dataclass

from ai.core.ai_model_list import AiModelList
from ai.core.ai_models import AiModels
from ai.core.ai_power import AiPower
from ai.core.ai_source import AiSource
from ai.core.ai_source_type import AiSourceType
from ai.prompt.ai_prompts import AiPrompt


class AiSetting:
    def __init__(
            self,
            model: AiModelList,
            source_type: AiSourceType,
            power: AiPower,
            remote_url: str | None = None,
            api_key: str | None = None,
    ):
        self.source: AiSource | None = None
        self.api_key = api_key
        self.model = model
        self.source_type = source_type
        self.remote_url = remote_url
        self.power = power

        self.check()
        self.setup()

    def setup(self):
        if self.model == AiModelList.LLAVA:
            self.source = AiModels.Llava.get_llava(self.power, self.source_type)
        elif self.model == AiModelList.OPEN_MISTRAL:
            self.source = AiModels.Mistral.get_open_mistral()
        elif self.model == AiModelList.PIXSTRAL:
            self.source = AiModels.Mistral.get_pixstral()
        elif self.model == AiModelList.GEMINI:
            self.source = AiModels.Gemini.get_flash()
        else:
            raise ValueError(f"Model not found: {self.model}.")


    def check(self):
        if self.source_type == AiSourceType.OLLAMA_SERVER and self.remote_url is None:
            raise ValueError("Remote URL is required for Ollama Server.")
        if self.source_type == AiSourceType.LMSTUDIO_SERVER and self.remote_url is None:
            raise ValueError("Remote URL is required for LM Studio Server.")
        if self.source_type == AiSourceType.API_MISTRAL and self.api_key is None:
            raise ValueError("API Key is required for Mistral API.")


@dataclass
class AiQuery:
    setting: AiSetting
    prompt: str
    payload_path: str | None = None