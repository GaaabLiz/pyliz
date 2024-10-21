from enum import Enum


class AiSourceType(Enum):
    OLLAMA_SERVER = "Ollama server",
    LMSTUDIO_SERVER = "LMM studio server",
    LOCAL_LLAMACPP = "Local (Llamacpp)",
    LOCAL_LLAMACPP_LIB = "Local (Official Llamacpp Library)"
    API_MISTRAL = "Mistral API"
    GEMINI = "Gemini"

