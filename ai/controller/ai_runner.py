from ai.controller.mistral_controller import MistralController
from ai.core.ai_inputs import AiInputs
from ai.core.ai_setting import AiSettings
from ai.core.ai_source_type import AiSourceType
from model.operation import Operation


class AiRunner:

    def __init__(self, settings: AiSettings, inputs: AiInputs):
        self.ai = settings
        self.inputs = inputs

    def __handle_mistral(self) -> Operation[str]:
        controller = MistralController(self.ai.api_key)
        return controller.run(self.ai, self.inputs.prompt, self.inputs.file_path)


    def run(self) -> Operation[str]:
        if self.ai.source_type == AiSourceType.API_MISTRAL:
            return self.__handle_mistral()
        raise NotImplementedError("Source type not implemented yet in AiRunner")