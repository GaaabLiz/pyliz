from dataclasses import dataclass, field
from enum import Enum
from math import isfinite
from typing import TypeVar

T = TypeVar("T")


@dataclass
class OperationInfo:
    """Describe an operation and its timing settings.

    Attributes:
        name: Operation name.
        description: Operation description.
        delay_each_task: Delay after each executed task, in seconds.
        estimated_duration: Optional positive estimate for the whole operation, in seconds,
            including any task delays.
    """

    name: str
    description: str
    delay_each_task: float = 0.0
    estimated_duration: float | None = field(default=None, kw_only=True)

    def __post_init__(self) -> None:
        if self.estimated_duration is not None and (not isfinite(self.estimated_duration) or self.estimated_duration <= 0):
            raise ValueError("estimated_duration must be a positive, finite number of seconds")


class OperationStatus(Enum):
    Pending = "Pending"
    InProgress = "In Progress"
    Completed = "Completed"
    Failed = "Failed"
    Cancelled = "Cancelled"
