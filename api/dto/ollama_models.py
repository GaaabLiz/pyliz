import json
from typing import Optional, List
from datetime import datetime


class Details:
    def __init__(self, parent_model: str, format: str, family: str, families: Optional[List[str]], parameter_size: str, quantization_level: str) -> None:
        self.parent_model = parent_model
        self.format = format
        self.family = family
        self.families = families
        self.parameter_size = parameter_size
        self.quantization_level = quantization_level

    def to_json(self) -> dict:
        return {
            "parent_model": self.parent_model,
            "format": self.format,
            "family": self.family,
            "families": self.families,
            "parameter_size": self.parameter_size,
            "quantization_level": self.quantization_level
        }

    @classmethod
    def from_json(cls, data: dict):
        return cls(
            parent_model=data.get("parent_model", ""),
            format=data.get("format", ""),
            family=data.get("family", ""),
            families=data.get("families", []),
            parameter_size=data.get("parameter_size", ""),
            quantization_level=data.get("quantization_level", "")
        )


class OllamaModel:
    def __init__(self, name: str, model: str, modified_at: datetime, size: int, digest: str, details: Details) -> None:
        self.name = name
        self.model = model
        self.modified_at = modified_at
        self.size = size
        self.digest = digest
        self.details = details

    def to_json(self) -> dict:
        return {
            "name": self.name,
            "model": self.model,
            "modified_at": self.modified_at.isoformat(),
            "size": self.size,
            "digest": self.digest,
            "details": self.details.to_json()
        }

    @classmethod
    def from_json(cls, data: dict):
        return cls(
            name=data.get("name", ""),
            model=data.get("model", ""),
            modified_at=datetime.fromisoformat(data.get("modified_at")),
            size=data.get("size", 0),
            digest=data.get("digest", ""),
            details=Details.from_json(data.get("details", {}))
        )


class OllamaModels:
    def __init__(self, models: List[OllamaModel]) -> None:
        self.models = models

    def to_json(self) -> dict:
        return {
            "models": [model.to_json() for model in self.models]
        }

    @classmethod
    def from_json(cls, data: dict):
        return cls(
            models=[OllamaModel.from_json(model_data) for model_data in data.get("models", [])]
        )


