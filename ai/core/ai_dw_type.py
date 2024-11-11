from enum import Enum


class AiDownloadType(Enum):
    PYTHON_LIB = "Python library",
    HG = "Huggingface model",
    WEB_FILES = "WEB files"