import logging
import sys
from typing import Any

from PySide6.QtWidgets import QMainWindow, QApplication, QWidget, QVBoxLayout, QPushButton

from pylizlib.qt.handler.operation_domain import RunnerInteraction
from pylizlib.qt.handler.operation_runner import OperationRunner
from pylizlib.qt.helper.operation import OperationDevDebug

logging.basicConfig(
    level=logging.DEBUG,  # o DEBUG, WARNING, ERROR, CRITICAL
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),  # stampa su stdout
        # logging.FileHandler("app.log")  # se vuoi anche scrivere su file
    ]
)

logger = logging.getLogger(__name__)


class OperationExampleWindow(QMainWindow):


    def __init__(self):
        super().__init__()
        self.setWindowTitle("Test Main Window")
        self.setGeometry(100, 100, 800, 600)

        self.interaction = OperationExampleInteraction()

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

    def start(self):
        runner = OperationRunner(
            interaction=self.interaction,
            max_threads=1,
        )
        runner.add(OperationDevDebug(self.interaction))
        runner.start()

    def stop(self):
        pass


class OperationExampleInteraction(RunnerInteraction):

    def on_op_eta_update(self, operation_id: str, eta: str):
        logger.debug(f"Operation {operation_id} ETA: {eta}")

    def on_op_finished(self, operation: Any):
        results = operation.get_task_results()

        for i, result in enumerate(results):
            logger.info(f"Risultato del task {i}: {result}")


if __name__ == '__main__':

    app = QApplication(sys.argv)
    window = OperationExampleWindow()
    window.show()
    sys.exit(app.exec())