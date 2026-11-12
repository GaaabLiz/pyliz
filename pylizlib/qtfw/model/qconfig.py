from pathlib import Path

from qfluentwidgets import ConfigValidator

from pylizlib.core.os.commands import is_software_installed


class ExecutableValidator(ConfigValidator):
    """Executable file validator"""

    def validate(self, value):
        path = Path(value)
        return is_software_installed(path)

    def correct(self, value):
        path = Path(value)
        if not is_software_installed(path):
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
