
class AiScanSettings:

    def __init__(
            self,
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
        self.ai_ocr = ai_ocr

    def set_all_true(self):
        self.ai_tags = True
        self.ai_file_metadata = True
        self.ai_comment = True
        self.ai_rename = True
        self.ai_ocr = True
