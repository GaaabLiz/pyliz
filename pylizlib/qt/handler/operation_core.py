from math import ceil
from time import perf_counter, sleep
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, Signal

from pylizlib.core.data.gen import gen_random_string
from pylizlib.core.handler.progress import (
    QueueProgress,
    QueueProgressMode,
    get_step_progress_percentage,
)
from pylizlib.core.log.pylizLogger import logger
from pylizlib.qt.handler.operation_domain import OperationInfo, OperationStatus


class Task(QObject):
    task_update_status = Signal(str, OperationStatus)
    task_update_progress = Signal(str, int)
    task_update_message = Signal(str, str)

    def __init__(self, name: str, abort_all_on_error: bool = True):
        super().__init__()
        self.id = gen_random_string(10)
        self.name = name
        self.abort_all_on_error = abort_all_on_error
        self.status = OperationStatus.Pending
        self.on_progress_changed = None
        self.result: Any = None
        self.progress = 0
        self.is_cancelled = False

    def cancel(self):
        self.is_cancelled = True

    def execute(self):
        return None

    def update_task_status(self, status: OperationStatus):
        logger.debug('Updating task "%s" status: %s', self.name, status)
        self.status = status
        self.task_update_status.emit(self.name, status)

    def update_task_progress(self, progress: int):
        logger.debug('Updating task "%s" progress: %s', self.name, progress)
        self.progress = progress
        self.task_update_progress.emit(self.name, progress)
        if self.on_progress_changed:
            self.on_progress_changed(self.name, progress)

    def update_task_message(self, message: str):
        self.task_update_message.emit(self.name, message)

    def gen_update_task_progress(self, current: int, total: int):
        self.update_task_progress(get_step_progress_percentage(current, total))


class GenericTask(Task):
    def __init__(self, name: str, func: Callable):
        super().__init__(name)
        self.func = func

        import inspect

        sig = inspect.signature(self.func)
        self.supports_progress = len(sig.parameters) == 1

    def execute(self):
        if self.supports_progress:
            return self.func(self)
        return self.func()


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
    def __init__(self, tasks: list[Task], op_info: OperationInfo):
        super().__init__()
        self.signals = OperationSignals()
        self.id = gen_random_string(10)
        self.info = op_info
        self.status = OperationStatus.Pending

        self.tasks = tasks
        self.progress = 0
        self.running = False
        self.error = None
        self.task_errors: list[str] = []
        self._is_cancelled = False
        self.progress_obj = QueueProgress(QueueProgressMode.SINGLE, len(tasks))
        self.finished_callback: Callable | None = None
        self.op_progress_update_callback: Callable | None = None
        self.current_task: Task | None = None

        self.time_started = None
        self.time_elapsed = 0
        self.time_finished = None
        self.time_estimated_total = 0
        self.time_estimated_remaining = 0
        self._eta_first_sample: tuple[int, float] | None = None
        self._eta_progress = 0
        self._eta_seconds: int | None = None

        for task in tasks:
            self.progress_obj.add_single(task.name)
            task.task_update_status.connect(self.signals.task_update_status)
            task.task_update_progress.connect(self.signals.task_update_progress)
            task.task_update_message.connect(self.signals.task_update_message)

    def execute_tasks(self):
        for task in self.tasks:
            if self._is_cancelled or task.is_cancelled:
                task.update_task_status(OperationStatus.Cancelled)
                self.signals.task_finished.emit(task.name)
                continue
            try:
                task.on_progress_changed = self.on_task_progress_update
                self.signals.task_start.emit(task.name)
                task.update_task_status(OperationStatus.InProgress)
                logger.debug("Executing task: %s", task.name)
                self.current_task = task
                result = task.execute()
                task.result = result
                if self._is_cancelled or task.is_cancelled:
                    task.update_task_status(OperationStatus.Cancelled)
                else:
                    task.update_task_progress(100)
                    task.update_task_status(OperationStatus.Completed)
            except Exception as e:
                task.update_task_status(OperationStatus.Failed)
                logger.error("Error in task %s: %s", task.name, e)
                self.signals.task_failed.emit(task.name, str(e))
                self.task_errors.append(f"Task {task.name} failed: {e}")
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
            if self.task_errors:
                self.error = "; ".join(self.task_errors)
                self.update_op_status(OperationStatus.Failed)
            elif self._is_cancelled or any(task.is_cancelled for task in self.tasks):
                self.update_op_status(OperationStatus.Cancelled)
            else:
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

    def stop(self):
        self._is_cancelled = True
        for task in self.tasks:
            task.cancel()

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
        if self.running:
            self.__update_eta()
        self.signals.op_update_progress.emit(self.id, progress)
        if self.op_progress_update_callback:
            self.op_progress_update_callback(self.id, self.progress)
        self.signals.op_update.emit(self)

    def __update_times(self):
        if self.running:
            self.time_elapsed = perf_counter() - self.time_started
        elif self.time_started is not None and self.time_finished is not None:
            self.time_elapsed = self.time_finished - self.time_started

    def __update_eta(self) -> None:
        if self.progress >= 100:
            self.time_estimated_remaining = max(0.0, self.info.delay_each_task)
            self.time_estimated_total = self.time_elapsed + self.time_estimated_remaining
            self.__set_eta_seconds(ceil(self.time_estimated_remaining))
            return

        if self.progress > self._eta_progress:
            self._eta_progress = self.progress
            if self._eta_first_sample is None:
                # Start measuring throughput after the first report to exclude startup work.
                self._eta_first_sample = (self.progress, self.time_elapsed)
            else:
                first_progress, first_elapsed = self._eta_first_sample
                observed_progress = self.progress - first_progress
                observed_duration = self.time_elapsed - first_elapsed
                if self.info.estimated_duration is not None:
                    initial_weight = 10  # Percentage points of work.
                    observed_progress += initial_weight
                    observed_duration += (self.info.estimated_duration / 100) * initial_weight
                seconds_per_percent = observed_duration / observed_progress
                self.time_estimated_total = self.time_elapsed + seconds_per_percent * (100 - self.progress)

        if self.time_estimated_total > 0:
            remaining = max(0, self.time_estimated_total - self.time_elapsed)
            self.time_estimated_remaining = remaining
            seconds = max(1, ceil(remaining))
            # Require a quarter-second margin to move the displayed countdown up.
            if self._eta_seconds and seconds > self._eta_seconds and remaining <= self._eta_seconds + 0.25:
                seconds = self._eta_seconds
            self.__set_eta_seconds(seconds)

    def __set_eta_seconds(self, seconds: int | None) -> None:
        if seconds != self._eta_seconds:
            self._eta_seconds = seconds
            self.signals.op_eta_update.emit(self.id, self.get_eta_formatted())

    def set_finished_callback(self, callback: Callable):
        self.finished_callback = callback

    def set_op_progress_callback(self, callback: Callable):
        self.op_progress_update_callback = callback

    def set_operation_started(self):
        logger.info("Starting operation %s", self.id)
        self.time_started = perf_counter()
        self.time_finished = None
        self.time_elapsed = 0
        self.time_estimated_total = self.info.estimated_duration or 0
        self.time_estimated_remaining = self.time_estimated_total
        self._eta_progress = 0
        self._eta_first_sample = None
        self._eta_seconds = ceil(self.time_estimated_total) if self.time_estimated_total else None
        self.running = True
        self.signals.op_start.emit()
        if self._eta_seconds is not None:
            self.signals.op_eta_update.emit(self.id, self.get_eta_formatted())

    def set_operation_finished(self):
        logger.info("Finishing operation %s", self.id)
        self.running = False
        self.time_finished = perf_counter()
        self.__update_times()
        self.time_estimated_total = self.time_elapsed
        self.time_estimated_remaining = 0
        self.__set_eta_seconds(0 if self.is_completed() else None)
        if self.finished_callback:
            self.finished_callback()
        self.signals.op_finished.emit(self)

    def get_elapsed_formatted(self) -> str:
        """Restituisce il tempo trascorso nel formato mm:ss"""
        minutes = int(self.time_elapsed) // 60
        seconds = int(self.time_elapsed) % 60
        return f"{minutes:02.0f}:{seconds:02.0f}"

    def get_eta_formatted(self) -> str:
        """Return the remaining time as mm:ss, or --:-- when unavailable."""
        if self._eta_seconds is None:
            return "--:--"

        minutes, seconds = divmod(self._eta_seconds, 60)
        return f"{minutes:02}:{seconds:02}"

    def is_failed(self):
        return self.status == OperationStatus.Failed

    def is_cancelled(self):
        return self.status == OperationStatus.Cancelled or self._is_cancelled or any(task.is_cancelled for task in self.tasks)

    def is_in_progress(self):
        return self.status == OperationStatus.InProgress

    def is_completed(self):
        return self.status == OperationStatus.Completed

    def is_pending(self):
        return self.status == OperationStatus.Pending
