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

    @staticmethod
    def clean_json_apici(json_string):
        # Rimuovi il prefisso '''json
        if json_string.startswith("```json"):
            json_string = json_string[len("```json"):]
        # Rimuovi il suffisso ''' se presente
        if json_string.endswith("```"):
            json_string = json_string[:-len("```")]
        # Elimina eventuali spazi bianchi in eccesso
        json_string = json_string.strip()
        # Carica il JSON
        return json_string

