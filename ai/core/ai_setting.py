from dataclasses import dataclass
from enum import Enum

from ai.core.ai_model_list import AiModelList
from ai.core.ai_models import AiModels
from ai.core.ai_power import AiPower
from ai.core.ai_source import AiSource
from ai.core.ai_source_type import AiSourceType
from ai.prompt.ai_prompts import AiPrompt
from util import fileutils


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
        elif self.model == AiModelList.WHISPER:
            self.source = AiModels.Whisper.get_whisper(self.power)
        else:
            raise ValueError(f"Model not found: {self.model}.")


    def check(self):
        if self.source_type == AiSourceType.OLLAMA_SERVER and self.remote_url is None:
            raise ValueError("Remote URL is required for Ollama Server.")
        if self.source_type == AiSourceType.LMSTUDIO_SERVER and self.remote_url is None:
            raise ValueError("Remote URL is required for LM Studio Server.")
        if self.source_type == AiSourceType.API_MISTRAL and self.api_key is None:
            raise ValueError("API Key is required for Mistral API.")


class AiQueryType(Enum):
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"



class AiQuery:
    setting: AiSetting
    prompt: str | None
    payload_path: str | None = None

    def __init__(self, setting: AiSetting, prompt: str | None, payload_path: str | None = None):
        self.setting = setting
        self.prompt = prompt
        self.payload_path = payload_path
        self.query_type = None

        if self.payload_path is not None:
            if fileutils.is_image_file(self.payload_path):
                self.query_type = AiQueryType.IMAGE
            elif fileutils.is_video_file(self.payload_path):
                self.query_type = AiQueryType.VIDEO
            elif fileutils.is_audio_file(self.payload_path):
                self.query_type = AiQueryType.AUDIO
        else:
            self.query_type = AiQueryType.TEXT