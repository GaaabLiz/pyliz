import unittest
from unittest.mock import patch

from pylizlib.core.handler.progress import (
    OperationProgress,
    ProgressHandler,
    QueueProgress,
    QueueProgressMode,
    TaskProgress,
    get_step_progress_percentage,
)


class OperationProgressTestCase(unittest.TestCase):
    def test_set_task_progress_updates_existing_task(self):
        operation = OperationProgress(
            operation_id="op1",
            operation_progress=0,
            operation_tasks=[TaskProgress("t1", 0), TaskProgress("t2", 0)],
        )

        operation.set_task_progress("t2", 80)

        self.assertEqual(operation.operation_tasks[1].task_progress, 80)

    def test_set_task_progress_logs_warning_for_missing_task(self):
        operation = OperationProgress(
            operation_id="op1",
            operation_progress=0,
            operation_tasks=[TaskProgress("t1", 0)],
        )

        with patch("pylizlib.core.handler.progress.logger.warning") as mock_warning:
            operation.set_task_progress("missing", 20)

        mock_warning.assert_called_once()

    def test_get_operation_progress_average(self):
        operation = OperationProgress(
            operation_id="op1",
            operation_progress=0,
            operation_tasks=[TaskProgress("t1", 20), TaskProgress("t2", 60)],
        )

        self.assertEqual(operation.get_operation_progress(), 40)

    def test_get_operation_progress_empty_tasks(self):
        operation = OperationProgress(
            operation_id="op1",
            operation_progress=0,
            operation_tasks=[],
        )

        self.assertEqual(operation.get_operation_progress(), 0)


class ProgressHandlerTestCase(unittest.TestCase):
    def test_add_and_get_operation_progress(self):
        handler = ProgressHandler()
        handler.add_operation("op1", ["t1", "t2"])
        handler.set_task_progress("op1", "t1", 50)
        handler.set_task_progress("op1", "t2", 100)

        self.assertEqual(handler.get_operation_progress("op1"), 75)

    def test_get_master_progress_multiple_operations(self):
        handler = ProgressHandler()
        handler.add_operation("op1", ["t1"])
        handler.add_operation("op2", ["t2"])
        handler.set_task_progress("op1", "t1", 100)
        handler.set_task_progress("op2", "t2", 0)

        self.assertEqual(handler.get_master_progress(), 50)

    def test_get_master_progress_empty(self):
        handler = ProgressHandler()
        self.assertEqual(handler.get_master_progress(), 0)

    def test_get_operation_progress_missing(self):
        handler = ProgressHandler()
        self.assertEqual(handler.get_operation_progress("missing_op"), 0)

    def test_empty_operation_and_unknown_operation_fallbacks(self):
        op = OperationProgress(operation_id="op_empty", operation_progress=0, operation_tasks=[])
        self.assertEqual(op.get_operation_progress(), 0)

        handler = ProgressHandler()
        # Empty handler master progress
        self.assertEqual(handler.get_master_progress(), 0)

        # Unknown operation query returns 0
        self.assertEqual(handler.get_operation_progress("unknown_op"), 0)

        # Private task lookup helper
        handler.add_operation("op1", ["t1", "t2"])
        task = handler._ProgressHandler__get_operation_task("t2")
        self.assertIsNotNone(task)
        self.assertEqual(task.task_id, "t2")
        self.assertIsNone(handler._ProgressHandler__get_operation_task("nonexistent"))


class QueueProgressTestCase(unittest.TestCase):
    def test_step_mode_progress(self):
        queue = QueueProgress(mode=QueueProgressMode.STEP, total_count=2)
        queue.set_step_progress(0, 100)
        queue.set_step_progress(1, 50)

        self.assertEqual(queue.get_step_progress(0), 100)
        self.assertEqual(queue.get_total_progress(), 75)

    def test_single_mode_progress(self):
        queue = QueueProgress(mode=QueueProgressMode.SINGLE, total_count=2)
        queue.add_single("a")
        queue.add_single("b")
        queue.set_single_progress("a", 100)
        queue.set_single_progress("b", 25)

        self.assertEqual(queue.get_single_progress("a"), 100)
        self.assertEqual(queue.get_total_progress(), 62)

    def test_total_progress_with_zero_count(self):
        queue = QueueProgress(mode=QueueProgressMode.STEP, total_count=0)
        self.assertEqual(queue.get_total_progress(), 0)

    def test_get_step_progress_missing(self):
        queue = QueueProgress(mode=QueueProgressMode.STEP, total_count=2)
        self.assertEqual(queue.get_step_progress(99), 0)

    def test_get_single_progress_missing(self):
        queue = QueueProgress(mode=QueueProgressMode.SINGLE, total_count=2)
        self.assertEqual(queue.get_single_progress("non_existent"), 0)

    def test_missing_step_or_single_returns_zero(self):
        queue_step = QueueProgress(mode=QueueProgressMode.STEP, total_count=2)
        self.assertEqual(queue_step.get_step_progress(999), 0)

        queue_single = QueueProgress(mode=QueueProgressMode.SINGLE, total_count=2)
        self.assertEqual(queue_single.get_single_progress("unknown"), 0)


class StepProgressFunctionTestCase(unittest.TestCase):
    def test_get_step_progress_percentage(self):
        self.assertEqual(get_step_progress_percentage(3, 4), 75)

    def test_get_step_progress_percentage_raises(self):
        with self.assertRaises(ValueError):
            get_step_progress_percentage(1, 0)


if __name__ == "__main__":
    unittest.main()
