from enum import Enum


class AiPower(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    @staticmethod
    def get_llava_from_power(ai_power: str) -> str:
        if ai_power == AiPower.HIGH.value:
            return "llava:13b"
        elif ai_power == AiPower.MEDIUM.value:
            return "llava:13b"
        else:
            return "llava:7b"
