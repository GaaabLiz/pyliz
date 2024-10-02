from ai.core.ai_method import AiMethod
from ai.core.ai_model_list import AiModelList
from ai.core.ai_models import AiModels
from ai.core.ai_power import AiPower
from ai.core.ai_prompts import AiPrompt
from ai.core.ai_scan_settings import AiScanSettings
from ai.core.ai_source import AiSource
from ai.core.ai_source_type import AiSourceType


class AiSettings:
    def __init__(
            self,
            model: AiModelList,
            source_type: AiSourceType,
            power: AiPower,
            remote_url: str | None = None,
    ):
        self.source: AiSource | None = None
        #self.method = None

        self.model = model
        self.source_type = source_type
        self.remote_url = remote_url
        self.power = power

        self.check()
        self.setup()

    def __setup_llava(self):
        self.source = AiModels.Llava.get_llava(self.power, self.source_type)

    def setup(self):
        if self.model == AiModelList.LLAVA:
            self.__setup_llava()

    def check(self):
        if self.source_type == AiSourceType.OLLAMA_SERVER and self.remote_url is None:
            raise ValueError("Remote URL is required for Ollama Server.")
        if self.source_type == AiSourceType.LMSTUDIO_SERVER and self.remote_url is None:
            raise ValueError("Remote URL is required for LM Studio Server.")
