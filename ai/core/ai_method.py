from enum import Enum


class AiMethod(Enum):
    # LLAVA_OLLAMA = "LLAVA with ollama server"
    # LLAVA_LOCAL_LLAMACPP = "LLAVA with local power"
    # LLAVA_LLAMACPP_AFTER_OLLAMA = "LLAVA with ollama and llamacpp"

    LLAVA_OLLAMA_JSON = "LLAVA with ollama server"
    LLAVA_LLAMACPP_JSON = "LLAVA with local power"
