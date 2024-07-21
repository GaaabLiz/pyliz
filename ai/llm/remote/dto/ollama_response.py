import json
from typing import List, Dict, Any


class OllamaResponse:
    def __init__(self, model: str, created_at: str, response: str, done: bool,
                 done_reason: str, context: List[int], total_duration: int,
                 load_duration: int, prompt_eval_count: int,
                 prompt_eval_duration: int, eval_count: int, eval_duration: int):
        self.model = model
        self.created_at = created_at
        self.response = self.clean_response(response)
        self.done = done
        self.done_reason = done_reason
        self.context = context
        self.total_duration = total_duration
        self.load_duration = load_duration
        self.prompt_eval_count = prompt_eval_count
        self.prompt_eval_duration = prompt_eval_duration
        self.eval_count = eval_count
        self.eval_duration = eval_duration

    @staticmethod
    def clean_response(response: str) -> str:
        # Remove the backticks and the "json" prefix from the response string
        cleaned_response = response.strip("`")
        if cleaned_response.lower().startswith("json"):
            cleaned_response = cleaned_response[4:].strip()
        # Remove the remaining backticks and newline characters
        cleaned_response = cleaned_response.replace("```", "").strip()
        return cleaned_response.replace("json", "")

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> 'OllamaResponse':
        return cls(
            # TODO se da problemi mettere none a tutti i get
            model=data.get("model", ""),
            created_at=data.get("created_at", ""),
            response=data.get("response", ""),
            done=data.get("done", False),
            done_reason=data.get("done_reason", ""),
            context=data.get("context", []),
            total_duration=data.get("total_duration", 0),
            load_duration=data.get("load_duration", 0),
            prompt_eval_count=data.get("prompt_eval_count", 0),
            prompt_eval_duration=data.get("prompt_eval_duration", 0),
            eval_count=data.get("eval_count", 0),
            eval_duration=data.get("eval_duration", 0)
        )

    def __str__(self) -> str:
        return (
            f"Model: {self.model}\n"
            f"Created At: {self.created_at}\n"
            f"Response: {self.response}\n"
            f"Done: {self.done}\n"
            f"Done Reason: {self.done_reason}\n"
            f"Context: {self.context}\n"
            f"Total Duration: {self.total_duration}\n"
            f"Load Duration: {self.load_duration}\n"
            f"Prompt Eval Count: {self.prompt_eval_count}\n"
            f"Prompt Eval Duration: {self.prompt_eval_duration}\n"
            f"Eval Count: {self.eval_count}\n"
            f"Eval Duration: {self.eval_duration}\n"
        )