from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QPushButton, QFileDialog, QWidget


class PathLineSelector(QWidget):

    def __init__(self, parent=None, select_file=False):
        super().__init__(parent)

        self.select_file = select_file  # True per selezionare file, False per cartelle

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)  # Rimuove i margini

        self.line_edit = QLineEdit(self)
        self.button = QPushButton("...", self)

        self.layout.addWidget(self.line_edit)
        self.layout.addWidget(self.button)

        self.button.clicked.connect(self.open_dialog)

    def open_dialog(self):
        if self.select_file:
            path, _ = QFileDialog.getOpenFileName(self, "Select File")
        else:
            path = QFileDialog.getExistingDirectory(self, "Select Directory")

        if path:
            self.line_edit.setText(path)

    def text(self):
        return self.line_edit.text()

    def setText(self, text):
        self.line_edit.setText(text)

    def get_text_changed(self):
        return self.line_edit.textChanged

