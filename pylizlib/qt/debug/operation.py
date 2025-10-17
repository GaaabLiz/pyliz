import random
import time
from collections.abc import Callable
from dataclasses import dataclass

from pylizlib.core.log.pylizLogger import logger
from pylizlib.qt.handler.operation_core import Operation, Task
from pylizlib.qt.handler.operation_domain import OperationInfo


@dataclass
class DevDebugData:
    step_min: int = 1
    step_max: int = 100
    sleep_min: float = 0.1
    sleep_max: float = 1


class OperationDevDebug(Operation):


    # class TaskTemplate(Task):
    #
    #     def __init__(self, name: str, on_task_progress_changed: Callable):
    #         super().__init__(name, on_task_progress_changed)
    #         self.data = DevDebugData()
    #         self.steps = random.randint(self.data.step_min, self.data.step_max)
    #
    #     def execute(self):
    #         for i in range(self.steps):
    #             progress: int = int(((i + 1) / self.steps) * 100)
    #             self.update_task_progress(progress)
    #             logger.debug(f"Log test {i}...")
    #             sleep = random.uniform(self.data.sleep_min, self.data.sleep_max)
    #             time.sleep(sleep)
    #         return self.steps


    class TaskTemplate2(Task):

        def __init__(self, name: str):
            super().__init__(name)
            self.data = DevDebugData()
            self.steps = random.randint(self.data.step_min, self.data.step_max)

        def execute(self):
            for i in range(self.steps):
                progress: int = int(((i + 1) / self.steps) * 100)
                self.update_task_progress(progress)
                logger.debug(f"Log test {i}...")
                sleep = random.uniform(self.data.sleep_min, self.data.sleep_max)
                time.sleep(sleep)
            return self.steps


    def __init__(
            self,
    ):
        tasks = [
            self.TaskTemplate2("Task1", ),
            self.TaskTemplate2("Task2")
        ]
        info = OperationInfo(
            name="Dev Debug",
            description="Dev Debug operation",
        )
        super().__init__(tasks, info)


    def run(self, /):
        self.execute()

    def stop(self):
        pass