from enum import Enum


class AiMethod(Enum):
    LLAVA_OLLAMA = "LLAVA with ollama server"
    LLAVA_LOCAL_LLAMACPP = "LLAVA with local power"
