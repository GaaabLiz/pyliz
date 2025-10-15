import time
from typing import Callable

from PySide6.QtCore import QThreadPool

from pylizlib.core.handler.progress import QueueProgress, QueueProgressMode
from pylizlib.core.log.pylizLogger import logger
from pylizlib.qt.handler.operation_core import Operation
from pylizlib.qt.handler.operation_domain import RunnerInteraction


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
