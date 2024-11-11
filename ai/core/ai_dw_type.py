from enum import Enum


class AiDownloadType(Enum):
    PYTHON_LIB = "Python library",
    HG = "Huggingface model",
    URL = "URL"