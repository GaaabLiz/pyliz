from pydantic import BaseModel


class AiPayloadMediaInfo(BaseModel):
    description: str
    tags: list[str]
    filename: str
    text: list[str]

    def __str__(self):
        return f"Description: {self.description}, Tags: {self.tags}, Filename: {self.filename}, Text: {self.text}"

    class Config:
        extra = "ignore"

