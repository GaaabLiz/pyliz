from dataclasses import dataclass
from enum import Enum
from typing import TypeVar, Any

T = TypeVar("T")


@dataclass
class OperationInfo:
    name: str
    description: str
    delay_each_task: float = 0.0


class OperationStatus(Enum):
    Pending = "Pending"
    InProgress = "In Progress"
    Completed = "Completed"
    Failed = "Failed"
