"""JSON utility helpers."""

import json
from json import JSONDecodeError
from typing import Any


class JsonUtils:
    """Collection of static helpers to validate and inspect JSON strings."""

    @staticmethod
    def is_valid_json(json_str: str) -> bool:
        """Return ``True`` when the input string contains valid JSON."""

        try:
            json.loads(json_str)
            return True
        except (TypeError, JSONDecodeError):
            return False

    @staticmethod
    def has_keys(json_str: str, keys: list[str]) -> bool:
        """Check whether a JSON object string contains all expected keys.

        :param json_str: JSON string to parse.
        :param keys: Keys that must exist at top-level.
        :return: ``True`` only when parsed JSON is an object containing all keys.
        """

        try:
            json_obj: Any = json.loads(json_str)
            if not isinstance(json_obj, dict):
                return False
            for key in keys:
                if key not in json_obj:
                    return False
            return True
        except (TypeError, JSONDecodeError):
            return False

    @staticmethod
    def clean_json_apici(json_string: str) -> str:
        """Remove optional Markdown code fences around JSON content.

        :param json_string: Raw string that may contain fenced JSON.
        :return: Trimmed JSON string without leading `````json`` or trailing `````.
        """

        if json_string.startswith("```json"):
            json_string = json_string[len("```json"):]
        elif json_string.startswith("```"):
            json_string = json_string[len("```"):]
        if json_string.endswith("```"):
            json_string = json_string[:-len("```")]
        json_string = json_string.strip()
        return json_string

