from ai.model.ai_method import AiMethod
from ai.model.ai_power import AiPower


class AiSettings:
    def __init__(
            self,
            method: AiMethod,
            power: AiPower,
            model_name: str | None = None,
            remote_url: str | None = None,
            ai_tags: bool = False,
            ai_file_metadata: bool = False,
            ai_comment: bool = False,
            ai_rename: bool = False,
            ai_ocr: bool = False,
    ):
        self.ai_tags = ai_tags
        self.ai_file_metadata = ai_file_metadata
        self.ai_comment = ai_comment
        self.ai_rename = ai_rename
        self.remote_url = remote_url
        self.method = method
        self.power = power
        self.model_name = model_name
        self.ai_ocr = ai_ocr

