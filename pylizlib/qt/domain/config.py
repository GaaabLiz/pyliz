from dataclasses import dataclass
from typing import Type, Any



@dataclass
class QtConfigItem:
    id: str
    type: Type
    default: Any
    max_list_size: int | None = None

