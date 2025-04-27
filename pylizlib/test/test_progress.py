import logging
import os
import unittest

from pylizlib.handler.progress import ProgressHandler


class TestProgress(unittest.TestCase):


    def test_1(self):
        progress = ProgressHandler()

        progress.add_operation("op1", ["task1", "task2"])
        progress.add_operation("op2", ["task3", "task4"])
        assert len(progress.operations) == 2
        assert progress.get_master_progress() == 0

        progress.set_task_progress("op1", "task1", 50)
        assert progress.get_operation_progress("op1") == 25

        progress.set_task_progress("op1", "task2", 100)
        assert progress.get_operation_progress("op1") == 75

        progress.set_task_progress("op2", "task3", 100)
        assert progress.get_operation_progress("op2") == 50
        progress.set_task_progress("op2", "task4", 100)
        assert progress.get_operation_progress("op2") == 100
        print(progress.get_master_progress())



if __name__ == '__main__':
    unittest.main()