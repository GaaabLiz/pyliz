from dataclasses import dataclass
from pathlib import Path

from qfluentwidgets import FluentIcon


@dataclass
class SoftwareData:
    path: Path
    is_service: bool
    icon: FluentIcon
    installed : bool
    running : bool
    version : str
