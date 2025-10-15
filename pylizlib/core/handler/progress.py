from dataclasses import dataclass
from enum import Enum

from pylizlib.core.log.pylizLogger import logger


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


@dataclass
class TaskProgress:
    task_id: str
    task_progress: int


@dataclass
class OperationProgress:
    operation_id: str
    operation_progress: float
    operation_tasks: list[TaskProgress]

    def set_task_progress(self, task_id: str, progress: int):
        for task in self.operation_tasks:
            if task.task_id == task_id:
                task.task_progress = progress
                return
        logger.warning("Task %s not found in operation %s", task_id, self.operation_id)

    def get_operation_progress(self):
        total_progress = sum(task.task_progress for task in self.operation_tasks)
        if self.operation_tasks:
            self.operation_progress = total_progress / len(self.operation_tasks)
        else:
            self.operation_progress = 0
        return self.operation_progress


class ProgressHandler:

    def __init__(self):
        self.operations: list[OperationProgress] = []

    def __get_operation_task(self, task_id: str):
        for operation in self.operations:
            for task in operation.operation_tasks:
                if task.task_id == task_id:
                    return task
        return None

    def add_operation(self, id: str, tasks_ids: list[str]):
        tasks = []
        for task_id in tasks_ids:
            tasks.append(TaskProgress(task_id=task_id, task_progress=0))
        self.operations.append(OperationProgress(
            operation_id=id,
            operation_progress=0,
            operation_tasks=tasks
        ))

    def set_task_progress(self, operation_id: str, task_id: str, progress: int):
        for operation in self.operations:
            if operation.operation_id == operation_id:
                operation.set_task_progress(task_id, progress)
                return

    def get_master_progress(self):
        total_progress = sum(operation.get_operation_progress() for operation in self.operations)
        if self.operations:
            return total_progress / len(self.operations)
        else:
            return 0

    def get_operation_progress(self, operation_id: str):
        for operation in self.operations:
            if operation.operation_id == operation_id:
                return operation.get_operation_progress()
        return 0


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



def get_step_progress_percentage(step_attuale: int, step_totali: int) -> int:
    """
    Calcola la percentuale di progresso come intero.

    Args:
        step_attuale: Numero di step completati
        step_totali: Numero totale di step dell'operazione

    Returns:
        Percentuale di progresso come intero (0-100)

    Raises:
        ValueError: Se step_totali è zero o negativo
    """
    if step_totali <= 0:
        raise ValueError("Il numero totale di step deve essere maggiore di zero")

    return int((step_attuale / step_totali) * 100)
