from PySide6.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout
import sys

class SimpleWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Widget Semplice PySide6")

        layout = QVBoxLayout()

        label = QLabel("Ciao, questo è un widget semplice!")
        layout.addWidget(label)

        self.setLayout(layout)