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
            prompt: AiPrompt,
            remote_url: str | None = None,
            scan_settings: AiScanSettings | None = None
    ):
        self.source: AiSource | None = None
        self.method: AiMethod | None = None

        self.model = model
        self.source_type = source_type
        self.remote_url = remote_url
        self.power = power
        self.prompt = prompt
        self.scan_settings = scan_settings

        self.setup()

    def __setup_llava(self):
        # Setting method based on source type
        if self.source_type == AiSourceType.OLLAMA_SERVER:
            self.method = AiMethod.LLAVA_OLLAMA
        elif self.source_type == AiSourceType.LOCAL_AI:
            self.method = AiMethod.LLAVA_LOCAL_LLAMACPP
        # Setting source
        self.source = AiModels.Llava.get_llava(self.power, self.method)

    def setup(self):
        if self.model == AiModelList.LLAVA:
            self.__setup_llava()

