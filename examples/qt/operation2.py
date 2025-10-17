import sys

from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QMainWindow

from pylizlib.qt.debug.operation import OperationDevDebug
from pylizlib.qt.handler.operation_core import Operation
from pylizlib.qt.handler.operation_domain import OperationInfo
from pylizlib.qt.handler.operation_runner import OperationRunner


class OperationExampleWindow(QMainWindow):


    def __init__(self):
        super().__init__()
        self.setWindowTitle("Test Main Window")
        self.setGeometry(100, 100, 800, 600)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Layout principale verticale (per centrare verticalmente)
        outer_layout = QVBoxLayout()
        outer_layout.addStretch()  # Spazio sopra
        button1 = QPushButton("START")
        button2 = QPushButton("STOP")
        button1.clicked.connect(self.start)
        button2.clicked.connect(self.stop)
        outer_layout.addWidget(button1)
        outer_layout.addWidget(button2)
        central_widget.setLayout(outer_layout)

    def on_runner_started(self):
        print("Runner started")

    def on_runner_finished(self, stats):
        print("Runner finished")

    def on_operation_finished(self, operation):
        results = operation.get_task_results()

        for i, result in enumerate(results):
            print(f"Result of task {i}: {result}")

    def on_operation_progress_update(self, operation_id: str, progress: int):
        print(f"Operation {operation_id} progress: {progress}%")

    def on_task_progress_update(self, task_name: str, progress: int):
        print(f"Task {task_name} progress: {progress}%")

    def start(self):
        runner = OperationRunner(
            max_threads=1,
        )
        runner.runner_start.connect(self.on_runner_started)
        runner.runner_finish.connect(self.on_runner_finished)
        runner.op_update_progress.connect(self.on_operation_progress_update)
        runner.task_update_progress.connect(self.on_task_progress_update)
        runner.op_finished.connect(self.on_operation_finished)


        op_info = OperationInfo("Test Operation", "Test operation description")
        op_tasks = [
            OperationDevDebug.TaskTemplate2("Task1"),
            OperationDevDebug.TaskTemplate2("Task2")
        ]
        op = Operation(op_tasks, op_info)
        runner.add(op)
        runner.start()

    def stop(self):
        pass


if __name__ == '__main__':

    app = QApplication(sys.argv)
    window = OperationExampleWindow()
    window.show()
    sys.exit(app.exec())