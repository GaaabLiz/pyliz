from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Protocol

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from pylizlib.media.lizmedia import LizMedia


class AiScanTool(str, Enum):
    """
    Enum representing the supported AI scan tool categories.
    Each category maps to a specialized provider.
    """

    TAGS = "TAGS"
    NSFW = "NSFW"
    OCR = "OCR"

    @classmethod
    def from_value(cls, value: str) -> "AiScanTool":
        """
        Maps a string identifier to an AiScanTool enum member.
        Handles normalization and common aliases (e.g. 'joytag' -> TAGS).
        """
        normalized = value.strip().upper().replace("_", "-")
        aliases = {
            "TAGS": cls.TAGS,
            "TAG": cls.TAGS,
            "JOYTAG": cls.TAGS,
            "TAGS-JOYTAG": cls.TAGS,
            "TAG-JOYTAG": cls.TAGS,
            "NSFW": cls.NSFW,
            "OCR": cls.OCR,
        }
        try:
            return aliases[normalized]
        except KeyError as exc:
            allowed = ", ".join(tool.value for tool in cls)
            raise ValueError(
                f"Unsupported AI scan tool '{value}'. Allowed values: {allowed}"
            ) from exc

    @classmethod
    def normalize_many(cls, values: list[str]) -> list["AiScanTool"]:
        """
        Normalizes a list of string tool identifiers into a unique list of AiScanTool enums.
        Ensures a single tool is not executed multiple times if redundant aliases are provided.
        """
        if not values:
            raise ValueError("At least one AI scan tool must be provided.")

        normalized: list[AiScanTool] = []
        seen: set[AiScanTool] = set()
        for value in values:
            tool = cls.from_value(value)
            if tool not in seen:
                normalized.append(tool)
                seen.add(tool)
        return normalized


@dataclass(slots=True)
class AiScanResult:
    """
    Data container for AI scan extraction results across different tool categories.
    """

    tags: list[str] | None = None
    nsfw: bool | None = None
    ocr_text: list[str] | None = None
    ocr_detected: bool | None = None

    def merge(self, other: "AiScanResult") -> "AiScanResult":
        """Merges another scan result into this one, overwriting non-None values."""
        if other.tags is not None:
            self.tags = other.tags
        if other.nsfw is not None:
            self.nsfw = other.nsfw
        if other.ocr_text is not None:
            self.ocr_text = other.ocr_text
        if other.ocr_detected is not None:
            self.ocr_detected = other.ocr_detected
        return self


class AiToolScanner(Protocol):
    """
    Protocol definition for an AI analysis provider plugin.
    """

    tool: AiScanTool

    def scan(self, media: "LizMedia") -> AiScanResult: ...


class AiPayloadMediaInfo(BaseModel):
    """
    Standard schema for media metadata payloads (tags, description, text, nsfw status).
    Used for serialization and API communication.
    """

    model_config = ConfigDict(extra="ignore")

    description: str
    tags: list[str]
    filename: str
    text: list[str]
    nsfw: bool | None = None
    ocr_detected: bool | None = None

    def __str__(self):
        return f"Description: {self.description}, Tags: {self.tags}, Filename: {self.filename}, Text: {self.text}"
