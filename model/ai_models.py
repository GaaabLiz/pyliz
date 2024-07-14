from model.ai_power import AiPower


class AiModels:
    def __init__(self):
        pass

    @staticmethod
    def get_llava_from_power(power: AiPower):
        if power == AiPower.LOW:
            return "llava:7b"
        elif power == AiPower.MEDIUM:
            return "llava:13b"
        else:
            return "llava:34b"

