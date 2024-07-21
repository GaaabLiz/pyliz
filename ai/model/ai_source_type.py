from enum import Enum


class AiSourceType(Enum):
    OLLAMA_SERVER = "Ollama Remote"
    LOCAL_AI = "Local AI"