from abc import ABC, abstractmethod
from enum import Enum


class PromptType(Enum):
    TEXT_PROMPT = "text_prompt"
    IMAGE_PROMPT = "image_prompt"


class CustomPrompt(ABC):

    prompt_type = None

    @property
    @abstractmethod
    def text(self):
        pass


class PromptInfo:

    def __init__(self, text: str, type: PromptType):
        self.text = text
        self.type = type
