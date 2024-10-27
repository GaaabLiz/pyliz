from enum import Enum

from ai.core.ai_model_list import AiModelList


class AiSourceType(Enum):
    OLLAMA_SERVER = "Ollama server",
    LMSTUDIO_SERVER = "LMM studio server",
    LOCAL_LLAMACPP = "Local (Llamacpp)",
    LOCAL_LLAMACPP_LIB = "Local (Official Llamacpp Library)"
    API_MISTRAL = "Mistral API"
    API_GEMINI = "Gemini API"


    def get_vision_models(self) -> list[AiModelList]:
        if self == AiSourceType.API_MISTRAL:
            return [
                AiModelList.PIXSTRAL
            ]

    def get_text_models(self) -> list[AiModelList]:
        if self == AiSourceType.API_MISTRAL:
            return [
                AiModelList.OPEN_MISTRAL
            ]

    def get_model_list(self) -> list[AiModelList]:
        array = []
        array.extend(self.get_vision_models())
        array.extend(self.get_text_models())
        return array

