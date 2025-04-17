from dataclasses import dataclass
from enum import Enum


class QueueProgressMode(Enum):
    STEP = "Step"
    SINGLE = "Single"


@dataclass
class QueueProgressItem:
    id: str
    progress: int = 0


@dataclass
class QueueProgressStep:
    step_number: int
    progress: int = 0



class QueueProgress:

    def __init__(
            self,
            mode: QueueProgressMode,
            total_count: int = 0,
            min_progress: int = 0,
            max_progress: int = 100,
    ):
        self.mode = mode
        self.total_count = total_count
        self.min_progress = min_progress
        self.max_progress = max_progress
        self.total_inner_progress = self.max_progress * total_count

        match self.mode:
            case QueueProgressMode.STEP:
                self.steps: list[QueueProgressStep] = []
                for i in range(self.total_count):
                    self.add_step(i)
            case QueueProgressMode.SINGLE:
                self.singles: list[QueueProgressItem] = []

    def add_step(self, step_number: int):
        self.steps.append(QueueProgressStep(step_number=step_number))

    def add_single(self, id: str):
        self.singles.append(QueueProgressItem(id=id))

    def set_step_progress(self, step_number: int, progress: int):
        for step in self.steps:
            if step.step_number == step_number:
                step.progress = progress
                return

    def set_single_progress(self, id: str, progress: int):
        for single in self.singles:
            if single.id == id:
                single.progress = progress
                return

    def get_step_progress(self, step_number: int):
        for step in self.steps:
            if step.step_number == step_number:
                return step.progress
        return 0

    def get_single_progress(self, id: str):
        for single in self.singles:
            if single.id == id:
                return single.progress
        return 0

    def get_total_progress(self):
        if self.total_count == 0:
            return 0
        total_progress = 0
        match self.mode:
            case QueueProgressMode.SINGLE:
                for single in self.singles:
                    total_progress += single.progress
            case QueueProgressMode.STEP:
                for step in self.steps:
                    total_progress += step.progress
        return int((total_progress / self.total_inner_progress) * 100)