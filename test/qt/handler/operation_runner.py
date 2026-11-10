import threading
import time
import unittest

from PySide6.QtCore import QCoreApplication

from pylizlib.qt.handler.operation_core import GenericTask, Operation
from pylizlib.qt.handler.operation_domain import OperationInfo, OperationStatus
from pylizlib.qt.handler.operation_runner import OperationRunner


class OperationRunnerTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def wait_until(self, predicate, timeout=3):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.processEvents()
            if predicate():
                return True
            time.sleep(0.005)
        self.app.processEvents()
        return predicate()

    def test_stopped_operation_skips_unstarted_tasks(self):
        executed = []
        operation = Operation(
            [
                GenericTask("first", lambda: executed.append("first")),
                GenericTask("second", lambda: executed.append("second")),
            ],
            OperationInfo("test", "test"),
        )

        operation.stop()
        operation.execute()

        self.assertEqual(executed, [])
        self.assertEqual(operation.status, OperationStatus.Cancelled)
        self.assertTrue(all(task.status == OperationStatus.Cancelled for task in operation.tasks))

    def test_stop_waits_for_running_worker_and_does_not_start_queued_operation(self):
        entered = threading.Event()
        release = threading.Event()
        finished = threading.Event()
        executed = []
        runner = OperationRunner(max_threads=1, on_runner_finished=finished.set)
        running = Operation(
            [
                GenericTask("blocking", lambda: (entered.set(), release.wait(3))),
                GenericTask("must be skipped", lambda: executed.append("after-stop")),
            ],
            OperationInfo("running", "running"),
        )
        queued = Operation(
            [GenericTask("queued", lambda: executed.append("queued"))],
            OperationInfo("queued", "queued"),
        )
        runner.adds([running, queued])

        runner.start()
        self.assertTrue(entered.wait(2))
        self.assertEqual(runner.active_operations, 1)
        runner.stop()
        self.assertEqual(runner.active_operations, 1)
        release.set()

        self.assertTrue(self.wait_until(finished.is_set))
        self.assertEqual(executed, [])
        self.assertEqual(runner.active_operations, 0)
        self.assertEqual(running.status, OperationStatus.Cancelled)
        self.assertEqual(queued.status, OperationStatus.Cancelled)

    def test_runner_finished_callback_runs_on_runner_thread(self):
        callback_threads = []
        finished = threading.Event()
        runner = OperationRunner(
            on_runner_finished=lambda: (callback_threads.append(threading.get_ident()), finished.set())
        )
        operation = Operation(
            [GenericTask("quick", lambda: None)],
            OperationInfo("quick", "quick"),
        )
        runner.add(operation)

        main_thread_id = threading.get_ident()
        runner.start()

        self.assertTrue(self.wait_until(finished.is_set))
        self.assertEqual(callback_threads, [main_thread_id])


if __name__ == "__main__":
    unittest.main()
