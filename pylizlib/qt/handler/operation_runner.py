from typing import Callable

from PySide6.QtCore import QObject, Qt, QThreadPool, Signal

from pylizlib.core.handler.progress import QueueProgress, QueueProgressMode
from pylizlib.core.log.pylizLogger import logger
from pylizlib.qt.handler.operation_core import Operation
from pylizlib.qt.handler.operation_domain import OperationStatus


class RunnerStatistics:
    def __init__(self, operations: list[Operation]):
        self.operations = operations
        self.total_operations = len(operations)
        self.completed_operations = 0
        self.failed_operations = 0
        self.cancelled_operations = 0
        self.pending_operations = 0
        self.total_progress = 0

        for operation in operations:
            if operation.is_completed():
                self.completed_operations += 1
            elif operation.is_failed():
                self.failed_operations += 1
            elif operation.status == OperationStatus.Cancelled:
                self.cancelled_operations += 1
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


# noinspection DuplicatedCode
class OperationRunner(QObject):
    runner_start = Signal()
    runner_finish = Signal(object)
    runner_stop = Signal()
    runner_update_progress = Signal(int)

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
    task_update_message = Signal(str, str)
    task_failed = Signal(str, str)
    task_finished = Signal(str)
    _operation_completed = Signal(object)

    def __init__(
        self,
        max_threads: int = 1,
        on_runner_finished: Callable | None = None,
        abort_all_on_error: bool = False,
    ):
        super().__init__()
        self.max_threads = max_threads
        self.thread_pool = QThreadPool(self)
        self.thread_pool.setMaxThreadCount(self.max_threads)
        self.operation_pool: list[Operation] = []
        self.active_operations = 0
        self.progress_obj: QueueProgress | None = None
        self.abort_all_on_error = abort_all_on_error
        self.on_runner_finished = on_runner_finished
        self._all_operations: list[Operation] = []
        self._stopping = False
        self._finished_emitted = False
        self._operation_completed.connect(
            self.on_operation_finished,
            Qt.ConnectionType.QueuedConnection,
        )

    def add(self, operation: Operation):
        self.operation_pool.append(operation)
        self._all_operations.append(operation)

        operation.signals.op_start.connect(self.op_start)
        operation.signals.op_update.connect(self.op_update)
        operation.signals.op_update_status.connect(self.op_update_status)
        operation.signals.op_update_progress.connect(self.op_update_progress)
        operation.signals.op_eta_update.connect(self.op_eta_update)
        operation.signals.op_failed.connect(self.op_failed)
        operation.signals.op_finished.connect(self.op_finished)

        operation.signals.task_start.connect(self.task_start)
        operation.signals.task_update_status.connect(self.task_update_status)
        operation.signals.task_update_progress.connect(self.task_update_progress)
        operation.signals.task_update_message.connect(self.task_update_message)
        operation.signals.task_failed.connect(self.task_failed)
        operation.signals.task_finished.connect(self.task_finished)

    def adds(self, operations: list[Operation]):
        for operation in operations:
            self.add(operation)

    def clear(self):
        """
        Clears the queue of pending operations and resets the runner.
        This method does not stop operations that are already running.
        """
        logger.info("Clearing pending operations from runner.")
        self.operation_pool.clear()
        self._all_operations.clear()
        self.progress_obj = None

    def start(self):
        self._stopping = False
        self._finished_emitted = False
        self.runner_start.emit()
        self.progress_obj = QueueProgress(QueueProgressMode.SINGLE, len(self.operation_pool))
        for op in self.operation_pool:
            self.progress_obj.add_single(op.id)
        initial_slots = min(
            len(self.operation_pool),
            max(0, self.thread_pool.maxThreadCount() - self.active_operations),
        )
        if initial_slots == 0 and not self.operation_pool and self.active_operations == 0:
            self.__set_runner_finished()
            return
        for _ in range(initial_slots):
            self.__start_next_operation()

    def stop(self):
        self.runner_stop.emit()
        self._stopping = True
        # Cancel all known operations so running ones can gracefully exit
        for op in self._all_operations:
            op.stop()
        self._cancel_pending_operations()
        if self.active_operations == 0:
            self.__set_runner_finished()

    def _cancel_pending_operations(self):
        for op in self.operation_pool:
            op.update_op_status(OperationStatus.Cancelled)
            for task in op.tasks:
                task.update_task_status(OperationStatus.Cancelled)
        self.operation_pool.clear()

    def __start_next_operation(self):
        can_start = not self._stopping and self.active_operations < self.thread_pool.maxThreadCount()
        if can_start and self.operation_pool:
            op = self.operation_pool.pop(0)
            op.set_finished_callback(lambda completed=op: self._operation_completed.emit(completed))
            op.set_op_progress_callback(self.on_op_progress_update)
            self.active_operations += 1
            try:
                self.thread_pool.start(op)
            except Exception:
                self.active_operations -= 1
                self.operation_pool.insert(0, op)
                raise

    def on_operation_finished(self, operation: Operation):
        self.active_operations -= 1
        if operation.is_completed():
            self.on_op_progress_update(operation.id, 100)
            self.op_update_progress.emit(operation.id, 100)

        if self.abort_all_on_error and operation.is_failed():
            logger.error("Operation %s failed, stopping all operations", operation.id)
            self._stopping = True
            for other_operation in self._all_operations:
                if other_operation is not operation:
                    other_operation.stop()
            self._cancel_pending_operations()
            if self.active_operations == 0:
                self.__set_runner_finished()
            return

        self.__start_next_operation()
        if self.active_operations == 0 and not self.operation_pool:
            self.__set_runner_finished()

    def __set_runner_finished(self):
        if self._finished_emitted:
            return
        self._finished_emitted = True
        statistics = RunnerStatistics(self._all_operations)
        self.runner_finish.emit(statistics)
        if self.on_runner_finished:
            self.on_runner_finished()

    def on_op_progress_update(self, op_id: str, op_progress: int):
        if self.progress_obj:
            self.progress_obj.set_single_progress(op_id, op_progress)
            self.runner_update_progress.emit(self.progress_obj.get_total_progress())
