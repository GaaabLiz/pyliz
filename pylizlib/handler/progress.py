from dataclasses import dataclass

from pylizlib.log.pylizLogger import logger


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

