import time
from abc import abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Protocol, TypeVar, Callable, Any

from PySide6.QtCore import QThreadPool, QRunnable

from pylizlib.core.data.gen import gen_random_string
from pylizlib.core.handler.progress import QueueProgressMode, QueueProgress
from pylizlib.core.log.pylizLogger import logger

T = TypeVar("T")


@dataclass
class OperationInfo:
    name: str
    description: str


class OperationStatus(Enum):
    Pending = "Pending"
    InProgress = "In Progress"
    Completed = "Completed"
    Failed = "Failed"


class RunnerInteraction(Protocol):
    def on_runner_start(self): ...
    def on_runner_finish(self, statistics: 'RunnerStatistics'): ...
    def on_runner_stop(self): ...
    def on_runner_update_progress(self, progress: int): ...

    def on_op_start(self): ...
    def on_op_update(self, operation: Any): ...
    def on_op_update_status(self, operation_id: str, status: OperationStatus): ...
    def on_op_update_progress(self, operation_id: str, progress: int): ...
    def on_op_eta_update(self, operation_id: str, eta: str): ...
    def on_op_failed(self, operation_id: str, error: str): ...
    def on_op_finished(self, operation: Any): ...

    def on_task_start(self, task_name: str): ...
    def on_task_update_status(self, task_name: str, status: OperationStatus): ...
    def on_task_update_progress(self, task_name: str, progress: int): ...
    def on_task_failed(self, task_name: str, error: str): ...
    def on_task_finished(self, task_name: str): ...


class Task:

    def __init__(
            self,
            name: str,
            on_progress_changed: Callable[[str, int], None],
            abort_all_on_error: bool = True,
            interaction: RunnerInteraction | None = None
    ):
        self.interaction = interaction
        self.name = name
        self.abort_all_on_error = abort_all_on_error
        self.status = OperationStatus.Pending
        self.on_progress_changed = on_progress_changed
        self.result: Any = None
        self.progress = 0

    def execute(self):
        return None

    def update_task_status(self, status: OperationStatus):
        logger.debug("Updating task \"%s\" status: %s", self.name, status)
        self.status = status
        self.interaction.on_task_update_status(self.name, status) if self.interaction else None

    def update_task_progress(self, progress: int):
        logger.debug("Updating task \"%s\" progress: %s", self.name, progress)
        self.progress = progress
        self.interaction.on_task_update_progress(self.name, progress) if self.interaction else None
        self.on_progress_changed(self.name, progress)


class Operation(QRunnable):

    def __init__(
            self,
            tasks: list[Task],
            op_info: OperationInfo,
            interaction: RunnerInteraction | None = None,
    ):
        super().__init__()
        self.id = gen_random_string(10)
        self.info = op_info
        self.status = OperationStatus.Pending

        self.tasks = tasks
        self.progress = 0
        self.running = False
        self.error = None
        self.progress_obj = QueueProgress(QueueProgressMode.SINGLE, len(tasks))
        self.interaction = interaction
        self.finished_callback: Callable | None = None
        self.op_progress_update_callback: Callable | None = None
        self.current_task: Task | None = None

        self.time_started = None
        self.time_elapsed = 0
        self.time_finished = None
        self.time_estimated_total = 0
        self.time_estimated_remaining = 0

        for task in tasks:
            self.progress_obj.add_single(task.name)


    def execute_tasks(self):
        for task in self.tasks:
            try:
                self.interaction.on_task_start(task.name) if self.interaction else None
                task.update_task_status(OperationStatus.InProgress)
                logger.debug("Executing task: %s", task.name)
                self.current_task = task
                result = task.execute()
                task.result = result
                task.update_task_status(OperationStatus.Completed)
            except Exception as e:
                task.update_task_status(OperationStatus.Failed)
                logger.error("Error in task %s: %s", task.name, e)
                self.interaction.on_task_failed(task.name, str(e)) if self.interaction else None
                if task.abort_all_on_error:
                    raise RuntimeError(f"Task {task.name} failed: {e}")
            finally:
                self.interaction.on_task_finished(task.name) if self.interaction else None
                self.current_task = None


    def execute(self):
        try:
            self.set_operation_started()
            self.update_op_status(OperationStatus.InProgress)
            self.execute_tasks()
            self.update_op_status(OperationStatus.Completed)
        except Exception as e:
            self.update_op_status(OperationStatus.Failed)
            self.interaction.on_op_failed(self.id, str(e)) if self.interaction else None
            self.error = str(e)
            logger.error("Error in operation: %s", e)
        finally:
            self.set_operation_finished()


    def on_task_progress_update(self, task_name: str, progress: int):
        self.progress_obj.set_single_progress(task_name, progress)
        self.update_op_progress(self.progress_obj.get_total_progress())


    @abstractmethod
    def stop(self):
        pass

    def get_tasks_ids(self) -> list[str]:
        return [task.name for task in self.tasks]

    def get_task_results(self) -> list[Any]:
        return [task.result for task in self.tasks]

    def update_op_status(self, status: OperationStatus):
        logger.debug("Updating operation status: %s", status)
        self.status = status
        self.__update_times()
        self.interaction.on_op_update_status(self.id, status) if self.interaction else None
        self.interaction.on_op_update(self) if self.interaction else None

    def update_op_progress(self, progress: int):
        logger.debug("Updating operation progress: %s", progress)
        self.progress = progress
        self.__update_times()
        self.interaction.on_op_update_progress(self.id, progress) if self.interaction else None
        self.op_progress_update_callback(self.id, self.progress) if self.op_progress_update_callback else None
        self.interaction.on_op_update(self) if self.interaction else None

    def __update_times(self):
        if self.running:
            self.time_elapsed = time.perf_counter() - self.time_started
            if self.progress > 0:
                self.time_estimated_total = self.time_elapsed / (self.progress / 100)
                self.time_estimated_remaining = max(0, self.time_estimated_total - self.time_elapsed)
                self.interaction.on_op_eta_update(self.id, self.get_eta_formatted()) if self.interaction else None
        else:
            self.time_elapsed = self.time_finished - self.time_started

    def set_finished_callback(self, callback: Callable):
        self.finished_callback = callback

    def set_op_progress_callback(self, callback: Callable):
        self.op_progress_update_callback = callback

    def set_operation_started(self):
        logger.info("Starting operation %s", self.id)
        self.running = True
        self.interaction.on_op_start() if self.interaction else None
        self.time_started = time.perf_counter()
        self.__update_times()

    def set_operation_finished(self):
        logger.info("Finishing operation %s", self.id)
        self.running = False
        if self.finished_callback:
            self.finished_callback()
        self.interaction.on_op_finished(self) if self.interaction else None
        self.time_finished = time.perf_counter()

    def get_elapsed_formatted(self) -> str:
        """Restituisce il tempo trascorso nel formato mm:ss"""
        minutes = self.time_elapsed // 60
        seconds = self.time_elapsed % 60
        return f"{minutes:02}:{seconds:02}"

    def get_eta_formatted(self) -> str:
        """
        Restituisce il tempo stimato rimanente nel formato mm:ss.
        """
        if self.progress <= 0:
            return "--:--"

        minutes = int(self.time_estimated_remaining) // 60
        seconds = int(self.time_estimated_remaining) % 60
        return f"{minutes:02}:{seconds:02}"

    def is_failed(self):
        return self.status == OperationStatus.Failed

    def is_in_progress(self):
        return self.status == OperationStatus.InProgress

    def is_completed(self):
        return self.status == OperationStatus.Completed

    def is_pending(self):
        return self.status == OperationStatus.Pending


class RunnerStatistics:

    def __init__(self, operations: list[Operation]):
        self.operations = operations
        self.total_operations = len(operations)
        self.completed_operations = 0
        self.failed_operations = 0
        self.pending_operations = 0
        self.total_progress = 0

        for operation in operations:
            if operation.is_completed():
                self.completed_operations += 1
            elif operation.is_failed():
                self.failed_operations += 1
            elif operation.is_in_progress():
                self.total_progress += operation.progress
            elif operation.is_pending():
                self.pending_operations += 1

    def has_ops_failed(self):
        return self.failed_operations > 0

    def get_first_error(self):
        for operation in self.operations:
            if operation.is_failed():
                return operation.error
        return None


class OperationRunner:

    def __init__(
            self,
            interaction: RunnerInteraction,
            max_threads: int = 1,
            on_runner_finished: Callable | None = None,
            abort_all_on_error: bool = False,
    ):
        self.interaction = interaction
        self.max_threads = max_threads
        self.thread_pool = QThreadPool.globalInstance()
        self.thread_pool.setMaxThreadCount(self.max_threads)
        self.operation_pool: list[Operation] = []
        self.active_operations = 0
        self.progress_obj: QueueProgress | None = None
        self.abort_all_on_error = abort_all_on_error
        self.on_runner_finished = on_runner_finished


    def add(self, operation: Operation):
        self.operation_pool.append(operation)

    def start(self):
        self.interaction.on_runner_start()
        self.progress_obj = QueueProgress(QueueProgressMode.SINGLE, len(self.operation_pool))
        for op in self.operation_pool:
            self.progress_obj.add_single(op.id)
        for op in self.operation_pool:
            self.__start_next_operation()

    def stop(self):
        self.interaction.on_runner_stop()
        self.thread_pool.waitForDone()
        self.active_operations = 0
        self.operation_pool.clear()

    def __start_next_operation(self):
        can_start = self.active_operations < self.thread_pool.maxThreadCount()
        if can_start and self.operation_pool:
            op = self.operation_pool.pop(0)
            op.set_finished_callback(lambda: self.on_operation_finished(op))
            op.set_op_progress_callback(self.on_op_progress_update)
            self.thread_pool.start(op)
            self.active_operations += 1

    def on_operation_finished(self, operation: Operation):
        if self.abort_all_on_error and operation.is_failed():
            logger.error("Operation %s failed, stopping all operations", operation.id)
            self.__set_runner_finished()
            return
        self.active_operations -= 1
        self.__start_next_operation()
        if self.active_operations == 0 and not self.operation_pool:
            self.__set_runner_finished()

    def __set_runner_finished(self):
        time.sleep(1)
        statistics = RunnerStatistics(self.operation_pool)
        self.interaction.on_runner_finish(statistics)
        self.on_runner_finished() if self.on_runner_finished else None

    def on_op_progress_update(self, op_id: str, op_progress: int):
        self.progress_obj.set_single_progress(op_id, op_progress)
        self.interaction.on_runner_update_progress(self.progress_obj.get_total_progress())
