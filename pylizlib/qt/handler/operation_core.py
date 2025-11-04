import time
from abc import abstractmethod
from time import sleep
from typing import Callable, Any

from PySide6.QtCore import QRunnable, QObject, Signal

from pylizlib.core.data.gen import gen_random_string
from pylizlib.core.handler.progress import QueueProgress, QueueProgressMode, get_step_progress_percentage
from pylizlib.core.log.pylizLogger import logger
from pylizlib.qt.handler.operation_domain import OperationStatus, OperationInfo


class Task(QObject):
    task_update_status = Signal(str, OperationStatus)
    task_update_progress = Signal(str, int)
    task_update_message = Signal(str, str)

    def __init__(
            self,
            name: str,
            abort_all_on_error: bool = True,
    ):
        super().__init__()
        self.id = gen_random_string(10)
        self.name = name
        self.abort_all_on_error = abort_all_on_error
        self.status = OperationStatus.Pending
        self.on_progress_changed = None
        self.result: Any = None
        self.progress = 0

    def execute(self):
        return None

    def update_task_status(self, status: OperationStatus):
        logger.debug("Updating task \"%s\" status: %s", self.name, status)
        self.status = status
        self.task_update_status.emit(self.name, status)

    def update_task_progress(self, progress: int):
        logger.debug("Updating task \"%s\" progress: %s", self.name, progress)
        self.progress = progress
        self.task_update_progress.emit(self.name, progress)
        if self.on_progress_changed:
            self.on_progress_changed(self.name, progress)

    def gen_update_task_progress(self, current: int, total: int):
        self.update_task_progress(get_step_progress_percentage(current, total))


class OperationSignals(QObject):
    op_start = Signal()
    op_update = Signal(object)
    op_update_status = Signal(str, OperationStatus)
    op_update_progress = Signal(str, int)
    op_eta_update = Signal(str, str)
    op_failed = Signal(str, str)
    op_finished = Signal(object)

    task_start = Signal(str)
    task_update_status = Signal(str, OperationStatus)
    task_update_progress = Signal(str, int)
    task_failed = Signal(str, str)
    task_finished = Signal(str)
    task_update_message = Signal(str, str)


class Operation(QRunnable):

    def __init__(
            self,
            tasks: list[Task],
            op_info: OperationInfo,
    ):
        super().__init__()
        self.signals = OperationSignals()
        self.id = gen_random_string(10)
        self.info = op_info
        self.status = OperationStatus.Pending

        self.tasks = tasks
        self.progress = 0
        self.running = False
        self.error = None
        self.progress_obj = QueueProgress(QueueProgressMode.SINGLE, len(tasks))
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
            task.task_update_status.connect(self.signals.task_update_status)
            task.task_update_progress.connect(self.signals.task_update_progress)
            task.task_update_message.connect(self.signals.task_update_message)

    def execute_tasks(self):
        for task in self.tasks:
            try:
                task.on_progress_changed = self.on_task_progress_update
                self.signals.task_start.emit(task.name)
                task.update_task_status(OperationStatus.InProgress)
                logger.debug("Executing task: %s", task.name)
                self.current_task = task
                result = task.execute()
                task.result = result
                task.update_task_status(OperationStatus.Completed)
            except Exception as e:
                task.update_task_status(OperationStatus.Failed)
                logger.error("Error in task %s: %s", task.name, e)
                self.signals.task_failed.emit(task.name, str(e))
                if task.abort_all_on_error:
                    raise RuntimeError(f"Task {task.name} failed: {e}")
            finally:
                self.signals.task_finished.emit(task.name)
                self.current_task = None
                sleep(self.info.delay_each_task)

    def execute(self):
        try:
            self.set_operation_started()
            self.update_op_status(OperationStatus.InProgress)
            self.execute_tasks()
            self.update_op_status(OperationStatus.Completed)
        except Exception as e:
            self.update_op_status(OperationStatus.Failed)
            self.signals.op_failed.emit(self.id, str(e))
            self.error = str(e)
            logger.error("Error in operation: %s", e)
        finally:
            self.set_operation_finished()

    def on_task_progress_update(self, task_name: str, progress: int):
        self.progress_obj.set_single_progress(task_name, progress)
        self.update_op_progress(self.progress_obj.get_total_progress())

    def run(self, /):
        self.execute()

    @abstractmethod
    def stop(self):
        pass

    def get_tasks_ids(self) -> list[str]:
        return [task.name for task in self.tasks]

    def get_task_results(self) -> list[Any]:
        return [task.result for task in self.tasks]

    def get_task_result_by_name(self, task_name: str) -> Any:
        for task in self.tasks:
            if task.name == task_name:
                return task.result
        return None

    def get_task_result_by_id(self, task_id: str) -> Any:
        for task in self.tasks:
            if task.id == task_id:
                return task.result
        return None

    def update_op_status(self, status: OperationStatus):
        logger.debug("Updating operation status: %s", status)
        self.status = status
        self.__update_times()
        self.signals.op_update_status.emit(self.id, status)
        self.signals.op_update.emit(self)

    def update_op_progress(self, progress: int):
        logger.debug("Updating operation progress: %s", progress)
        self.progress = progress
        self.__update_times()
        self.signals.op_update_progress.emit(self.id, progress)
        if self.op_progress_update_callback:
            self.op_progress_update_callback(self.id, self.progress)
        self.signals.op_update.emit(self)

    def __update_times(self):
        if self.running:
            self.time_elapsed = time.perf_counter() - self.time_started
            if self.progress > 0:
                self.time_estimated_total = self.time_elapsed / (self.progress / 100)
                self.time_estimated_remaining = max(0, self.time_estimated_total - self.time_elapsed)
                self.signals.op_eta_update.emit(self.id, self.get_eta_formatted())
        else:
            if self.time_started and self.time_finished:
                self.time_elapsed = self.time_finished - self.time_started

    def set_finished_callback(self, callback: Callable):
        self.finished_callback = callback

    def set_op_progress_callback(self, callback: Callable):
        self.op_progress_update_callback = callback

    def set_operation_started(self):
        logger.info("Starting operation %s", self.id)
        self.running = True
        self.signals.op_start.emit()
        self.time_started = time.perf_counter()
        self.__update_times()

    def set_operation_finished(self):
        logger.info("Finishing operation %s", self.id)
        self.running = False
        self.time_finished = time.perf_counter()
        self.__update_times()
        if self.finished_callback:
            self.finished_callback()
        self.signals.op_finished.emit(self)

    def get_elapsed_formatted(self) -> str:
        """Restituisce il tempo trascorso nel formato mm:ss"""
        minutes = int(self.time_elapsed) // 60
        seconds = int(self.time_elapsed) % 60
        return f"{minutes:02.0f}:{seconds:02.0f}"

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