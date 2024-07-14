from ai.model.ai_method import AiMethod


class AiSettings:

    def __init__(
            self,
            ai_tags: bool,
            ai_file_metadata: bool,
            ai_comment: bool,
            ai_rename: bool,
            remote_url: str,
            method: AiMethod
    ):
        self.ai_tags = ai_tags
        self.ai_file_metadata = ai_file_metadata
        self.ai_comment = ai_comment
        self.ai_rename = ai_rename
        self.remote_url = remote_url
        self.method = method
