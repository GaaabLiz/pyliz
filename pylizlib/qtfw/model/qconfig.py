import os
from dataclasses import asdict
from pathlib import Path

from qfluentwidgets import ConfigValidator, ConfigSerializer, ConfigItem



class ExecutableValidator(ConfigValidator):
    """Executable file validator"""

    def validate(self, value):
        path = Path(value)
        # Controlla che il file esista ed è eseguibile
        return path.is_file() and os.access(path, os.X_OK)

    def correct(self, value):
        path = Path(value)
        # Se il file non esiste o non è eseguibile, ritorna valore senza modifiche
        if not path.exists() or not os.access(path, os.X_OK):
            return value
        # Ritorna il percorso assoluto con slashes forward
        return str(path.resolve()).replace("\\", "/")

class TextListValidator(ConfigValidator):
    """Text list validator - check non-empty strings"""

    def validate(self, value):
        # value is expected to be a list of strings
        return all(isinstance(i, str) and i.strip() != "" for i in value)

    def correct(self, value: list[str]):
        # Rimuove voci vuote o solo spazi
        return [i.strip() for i in value if isinstance(i, str) and i.strip() != ""]


def count_elements_in_settings_keys(data, key, group=None):
    total_count = 0

    groups_to_check = [group] if group else data.keys()

    for grp in groups_to_check:
        group_data = data.get(grp, {})
        if isinstance(group_data, dict) and key in group_data and isinstance(group_data[key], list):
            total_count += len(group_data[key])

    return total_count

