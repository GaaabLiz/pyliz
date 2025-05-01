from dataclasses import dataclass


@dataclass
class ConfigItem:
    id: str
    name: str
    section: str
    is_bool: bool = False
    default: str | bool | None = None
    values: list[str] | None = None
    min_value: str | None = None
    max_value: str | None = None
    require_reboot: bool = False