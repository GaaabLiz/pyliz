import json
from json import JSONDecodeError


class JsonUtils:

    @staticmethod
    def is_valid_json(json_str):
        """
        Verify if a string is a valid JSON.
        :param json_str: The string to verify.
        :return: True if the string is a valid JSON, False otherwise.
        """
        try:
            json.loads(json_str)
            return True
        except JSONDecodeError:
            return False

    @staticmethod
    def has_keys(json_str, keys: list[str]) -> bool:
        """
        Check if a JSON string contains all specified keys.
        :param json_str: The JSON string to check.
        :param keys: A list of keys to look for in the JSON.
        :return: True if all keys are present, False otherwise.
        """
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
        """
        Clean a JSON string by removing enclosing triple backticks and whitespace.
        :param json_string: The JSON string to clean.
        :return: The cleaned JSON string.
        """
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

