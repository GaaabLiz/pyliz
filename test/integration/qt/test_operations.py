import os
import unittest

import pytest

pytest.importorskip("PySide6.QtCore")

from PySide6.QtCore import QCoreApplication

from pylizlib.qt.handler.operation_core import GenericTask, Operation, Task
from pylizlib.qt.handler.operation_domain import OperationInfo, OperationStatus
from pylizlib.qt.handler.operation_runner import OperationRunner, RunnerStatistics

os.environ["QT_QPA_PLATFORM"] = "offscreen"
app = QCoreApplication.instance() or QCoreApplication([])


class TaskTestCase(unittest.TestCase):
    def test_task_lifecycle_and_signals(self):
        task = Task("lifecycle_task")
        self.assertEqual(task.name, "lifecycle_task")
        self.assertEqual(task.status, OperationStatus.Pending)
        self.assertFalse(task.is_cancelled)

        status_updates = []
        progress_updates = []
        message_updates = []

        task.task_update_status.connect(lambda name, status: status_updates.append((name, status)))
        task.task_update_progress.connect(lambda name, prog: progress_updates.append((name, prog)))
        task.task_update_message.connect(lambda name, msg: message_updates.append((name, msg)))

        task.update_task_status(OperationStatus.InProgress)
        self.assertEqual(task.status, OperationStatus.InProgress)
        self.assertEqual(status_updates[-1], ("lifecycle_task", OperationStatus.InProgress))

        task.update_task_progress(50)
        self.assertEqual(task.progress, 50)
        self.assertEqual(progress_updates[-1], ("lifecycle_task", 50))

        task.gen_update_task_progress(3, 4)
        self.assertEqual(task.progress, 75)

        task.update_task_message("Working on step 3")
        self.assertEqual(message_updates[-1], ("lifecycle_task", "Working on step 3"))

        task.cancel()
        self.assertTrue(task.is_cancelled)
        self.assertIsNone(task.execute())

    def test_generic_task_execution(self):
        # Without progress parameter
        t1 = GenericTask("add", lambda: 10 + 20)
        self.assertFalse(t1.supports_progress)
        self.assertEqual(t1.execute(), 30)

        # With progress parameter
        def worker_with_progress(task_inst):
            task_inst.update_task_progress(42)
            return "ok"

        t2 = GenericTask("worker", worker_with_progress)
        self.assertTrue(t2.supports_progress)
        self.assertEqual(t2.execute(), "ok")
        self.assertEqual(t2.progress, 42)


class OperationTestCase(unittest.TestCase):
    def test_operation_execution_success(self):
        results = []

        def task1_fn():
            results.append("task1")
            return "res1"

        def task2_fn():
            results.append("task2")
            return "res2"

        t1 = GenericTask("Task 1", task1_fn)
        t2 = GenericTask("Task 2", task2_fn)

        info = OperationInfo(name="Test Op", description="Op desc")
        op = Operation([t1, t2], info)

        op.execute_tasks()

        self.assertEqual(results, ["task1", "task2"])
        self.assertEqual(t1.status, OperationStatus.Completed)
        self.assertEqual(t2.status, OperationStatus.Completed)
        self.assertEqual(t1.result, "res1")
        self.assertEqual(t2.result, "res2")

    def test_operation_execution_aborts_on_error(self):
        def failing_fn():
            raise ValueError("Task blew up")

        def second_fn():
            pass

        t1 = GenericTask("Fail Task", failing_fn)
        t2 = GenericTask("Never Runs", second_fn)

        info = OperationInfo(name="Fail Op", description="Desc")
        op = Operation([t1, t2], info)

        with self.assertRaises(RuntimeError):
            op.execute_tasks()

        self.assertEqual(t1.status, OperationStatus.Failed)
        self.assertEqual(t2.status, OperationStatus.Pending)

    def test_operation_full_lifecycle_and_helpers(self):
        t1 = GenericTask("t1", lambda: "val1")
        t2 = GenericTask("t2", lambda: "val2")
        info = OperationInfo(name="Op Full", description="Full test")
        op = Operation([t1, t2], info)

        self.assertTrue(op.is_pending())
        self.assertFalse(op.is_in_progress())
        self.assertFalse(op.is_completed())
        self.assertFalse(op.is_failed())
        self.assertEqual(op.get_tasks_ids(), ["t1", "t2"])

        # Call execute directly
        finished_called = []
        progress_updates = []
        op.set_finished_callback(lambda: finished_called.append(True))
        op.set_op_progress_callback(lambda op_id, prog: progress_updates.append((op_id, prog)))

        op.execute()

        self.assertTrue(op.is_completed())
        self.assertEqual(finished_called, [True])
        self.assertEqual(op.get_task_results(), ["val1", "val2"])
        self.assertEqual(op.get_task_result_by_name("t1"), "val1")
        self.assertIsNone(op.get_task_result_by_name("unknown"))
        self.assertEqual(op.get_task_result_by_id(t1.id), "val1")
        self.assertIsNone(op.get_task_result_by_id("unknown_id"))

        # Elapsed and ETA formatting
        self.assertRegex(op.get_elapsed_formatted(), r"^\d{2}:\d{2}$")
        self.assertEqual(op.get_eta_formatted(), "00:00")

        # Test stop
        op.stop()
        self.assertTrue(t1.is_cancelled)
        self.assertTrue(t2.is_cancelled)

    def test_operation_failure_in_execute(self):
        def blowup():
            raise RuntimeError("Fatal op failure")

        t = GenericTask("fail", blowup)
        op = Operation([t], OperationInfo("Fail", "Desc"))
        op.run()  # delegates to execute()

        self.assertTrue(op.is_failed())
        self.assertIn("Fatal op failure", op.error)

    def test_operation_eta_formatted_when_zero_progress(self):
        op = Operation([], OperationInfo("Zero", "Desc"))
        op.progress = 0
        self.assertEqual(op.get_eta_formatted(), "--:--")


class RunnerStatisticsTestCase(unittest.TestCase):
    def test_statistics_aggregation(self):
        op_completed = Operation([], OperationInfo("Op1", ""))
        op_completed.status = OperationStatus.Completed

        op_failed = Operation([], OperationInfo("Op2", ""))
        op_failed.status = OperationStatus.Failed
        op_failed.error = "Boom"

        op_in_progress = Operation([], OperationInfo("Op3", ""))
        op_in_progress.status = OperationStatus.InProgress
        op_in_progress.progress = 50

        op_pending = Operation([], OperationInfo("Op4", ""))
        op_pending.status = OperationStatus.Pending

        stats = RunnerStatistics([op_completed, op_failed, op_in_progress, op_pending])
        self.assertEqual(stats.total_operations, 4)
        self.assertEqual(stats.completed_operations, 1)
        self.assertEqual(stats.failed_operations, 1)
        self.assertEqual(stats.pending_operations, 1)
        self.assertEqual(stats.total_progress, 50)
        self.assertTrue(stats.has_ops_failed())
        self.assertEqual(stats.get_first_error(), "Boom")


class OperationRunnerTestCase(unittest.TestCase):
    def test_runner_add_adds_and_clear(self):
        runner = OperationRunner(max_threads=1)
        op1 = Operation([], OperationInfo("Op1", ""))
        op2 = Operation([], OperationInfo("Op2", ""))

        runner.add(op1)
        self.assertEqual(len(runner.operation_pool), 1)

        runner.adds([op2])
        self.assertEqual(len(runner.operation_pool), 2)

        runner.clear()
        self.assertEqual(len(runner.operation_pool), 0)

    def test_runner_execution_and_completion(self):
        runner_finished_calls = []
        runner = OperationRunner(
            max_threads=2,
            on_runner_finished=lambda: runner_finished_calls.append(True),
            abort_all_on_error=False,
        )

        t1 = GenericTask("T1", lambda: "done1")
        t2 = GenericTask("T2", lambda: "done2")
        op1 = Operation([t1], OperationInfo("Op1", ""))
        op2 = Operation([t2], OperationInfo("Op2", ""))

        runner.adds([op1, op2])

        # Track signals
        started = []
        finished_stats = []
        progress_values = []
        runner.runner_start.connect(lambda: started.append(True))
        runner.runner_finish.connect(lambda stats: finished_stats.append(stats))
        runner.runner_update_progress.connect(lambda val: progress_values.append(val))

        runner.start()
        # Wait for thread pool to finish and process queued Qt signals
        runner.thread_pool.waitForDone()
        import time

        time.sleep(0.2)
        QCoreApplication.processEvents()

        self.assertEqual(started, [True])
        self.assertEqual(len(finished_stats), 1)
        self.assertEqual(finished_stats[0].completed_operations, 2)
        self.assertEqual(runner_finished_calls, [True])

    def test_runner_stop(self):
        runner = OperationRunner(max_threads=1)
        stopped_signals = []
        runner.runner_stop.connect(lambda: stopped_signals.append(True))

        t = GenericTask("T", lambda: "val")
        op = Operation([t], OperationInfo("Op", ""))
        runner.add(op)

        runner.stop()
        self.assertEqual(stopped_signals, [True])
        self.assertEqual(len(runner.operation_pool), 0)

    def test_runner_abort_all_on_error(self):
        runner = OperationRunner(max_threads=1, abort_all_on_error=True)

        def blowup():
            raise RuntimeError("Err in Op1")

        op1 = Operation([GenericTask("F", blowup)], OperationInfo("Op1", ""))
        op2 = Operation([GenericTask("Never", lambda: "ok")], OperationInfo("Op2", ""))

        runner.adds([op1, op2])
        runner.start()
        runner.thread_pool.waitForDone()
        import time

        time.sleep(0.2)
        QCoreApplication.processEvents()

        self.assertEqual(op1.status, OperationStatus.Failed)
        self.assertEqual(len(runner.operation_pool), 0)


if __name__ == "__main__":
    unittest.main()
