import json
from json import JSONDecodeError


class JsonUtils:

    @staticmethod
    def is_valid_json(json_str):
        try:
            json.loads(json_str)
            return True
        except JSONDecodeError:
            return False

    @staticmethod
    def has_keys(json_str, keys: list[str]) -> bool:
        try:
            json_obj = json.loads(json_str)
            for key in keys:
                if key not in json_obj:
                    return False
            return True
        except JSONDecodeError:
            return False

