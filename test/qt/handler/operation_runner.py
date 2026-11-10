import threading
import time
import unittest

from PySide6.QtCore import QCoreApplication
from PySide6.QtCore import QThreadPool

from pylizlib.qt.handler.operation_core import GenericTask, Operation
from pylizlib.qt.handler.operation_domain import OperationInfo, OperationStatus
from pylizlib.qt.handler.operation_runner import OperationRunner
from pylizlib.qt.handler.operation_runner import RunnerStatistics


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

    def test_fast_worker_is_counted_before_pool_submission(self):
        finished = threading.Event()
        runner = OperationRunner(on_runner_finished=finished.set)
        delegate_pool = QThreadPool()
        delegate_pool.setMaxThreadCount(1)
        observed_counts = []

        class WaitForWorkerPool:
            def maxThreadCount(self):
                return delegate_pool.maxThreadCount()

            def start(self, runnable):
                observed_counts.append(runner.active_operations)
                delegate_pool.start(runnable)
                self.finished = delegate_pool.waitForDone(2000)

        runner.thread_pool = WaitForWorkerPool()
        runner.add(Operation([GenericTask("quick", lambda: None)], OperationInfo("quick", "quick")))

        runner.start()

        self.assertEqual(observed_counts, [1])
        self.assertTrue(self.wait_until(finished.is_set))
        self.assertEqual(runner.active_operations, 0)

    def test_abort_waits_for_other_running_operations(self):
        failing_entered = threading.Event()
        fail_now = threading.Event()
        other_entered = threading.Event()
        release_other = threading.Event()
        finished = threading.Event()
        emitted_statistics = []
        cancellation_seen = []
        runner = OperationRunner(
            max_threads=2,
            on_runner_finished=finished.set,
            abort_all_on_error=True,
        )
        runner.runner_finish.connect(emitted_statistics.append)

        def fail_after_release():
            failing_entered.set()
            fail_now.wait(3)
            raise ValueError("expected failure")

        def remain_running(task):
            other_entered.set()
            release_other.wait(3)
            cancellation_seen.append(task.is_cancelled)

        failing = Operation(
            [GenericTask("failure", fail_after_release)],
            OperationInfo("failure", "failure"),
        )
        other = Operation(
            [GenericTask("other", remain_running)],
            OperationInfo("other", "other"),
        )
        runner.adds([failing, other])

        runner.start()
        self.assertTrue(failing_entered.wait(2))
        self.assertTrue(other_entered.wait(2))
        fail_now.set()

        self.assertTrue(
            self.wait_until(lambda: failing.is_failed() and runner.active_operations == 1)
        )
        self.assertFalse(finished.is_set())
        self.assertTrue(other.is_cancelled())

        release_other.set()
        self.assertTrue(self.wait_until(finished.is_set))
        self.assertEqual(runner.active_operations, 0)
        self.assertEqual(len(emitted_statistics), 1)
        self.assertEqual(emitted_statistics[0].failed_operations, 1)
        self.assertEqual(cancellation_seen, [True])

    def test_continued_task_failure_marks_operation_and_statistics_failed(self):
        later_task_ran = threading.Event()
        failed_task = GenericTask("recoverable failure", lambda: (_ for _ in ()).throw(ValueError("bad input")))
        failed_task.abort_all_on_error = False
        operation = Operation(
            [failed_task, GenericTask("later", later_task_ran.set)],
            OperationInfo("partial", "partial"),
        )

        operation.execute()
        statistics = RunnerStatistics([operation])

        self.assertTrue(later_task_ran.is_set())
        self.assertEqual(failed_task.status, OperationStatus.Failed)
        self.assertEqual(operation.status, OperationStatus.Failed)
        self.assertIn("recoverable failure", operation.error)
        self.assertEqual(statistics.failed_operations, 1)
        self.assertEqual(statistics.completed_operations, 0)

    def test_empty_batch_emits_start_finish_and_callback_once(self):
        starts = []
        finishes = []
        callback_calls = []
        runner = OperationRunner(on_runner_finished=lambda: callback_calls.append("finished"))
        runner.runner_start.connect(lambda: starts.append("started"))
        runner.runner_finish.connect(finishes.append)

        runner.start()

        self.assertEqual(starts, ["started"])
        self.assertEqual(len(finishes), 1)
        self.assertEqual(finishes[0].total_operations, 0)
        self.assertEqual(callback_calls, ["finished"])
        self.assertEqual(runner.active_operations, 0)


if __name__ == "__main__":
    unittest.main()
