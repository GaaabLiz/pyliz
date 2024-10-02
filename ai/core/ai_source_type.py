from enum import Enum


class AiSourceType(Enum):
    OLLAMA_SERVER = "Ollama Remote",
    LMSTUDIO_SERVER = "LMStudio Remote",
    # LOCAL_AI = "Local AI"
    LOCAL_LLAMACPP = "Local Llamacpp",
    LOCAL_LLAMACPP_LIB = "Local Llamacpp Library"