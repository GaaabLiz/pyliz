from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QVBoxLayout, QDialog
from qfluentwidgets import FluentStyleSheet, BodyLabel, ProgressBar


@dataclass
class SimpleProgressSettings:
    window_title: str = "Operazione in corso"
    window_label: str = "Attendere prego..."
    initial_status_text: str = "Inizializzazione..."
    window_width: int = 400
    window_height: int = 150


class SimpleProgressDialog(QDialog):
    """Dialog semplice con progress bar (CORRETTO)"""

    def __init__(self, parent=None, settings: SimpleProgressSettings = SimpleProgressSettings()):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle(self.settings.window_title)
        self.setFixedSize(self.settings.window_width, self.settings.window_height)

        # Imposta la modalità modale e rimuove il pulsante di chiusura dalla barra del titolo
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowCloseButtonHint)

        # Layout
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        # Titolo
        self.title = BodyLabel(self.settings.window_label, self)
        font = QFont()
        font.setPointSize(11)
        font.setBold(True)
        self.title.setFont(font)
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title)

        # Progress bar
        self.progress_bar = ProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        layout.addWidget(self.progress_bar)

        # Status
        self.status = BodyLabel(self.settings.initial_status_text, self)
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status)

        FluentStyleSheet.DIALOG.apply(self)

    def update_progress(self, value: int, text: str):
        self.progress_bar.setValue(value)
        self.status.setText(text)

    def set_maximum(self, max_val: int):
        self.progress_bar.setMaximum(max_val)

    def update_status_only(self, text: str):
        """Aggiorna solo il testo di stato senza cambiare il progresso"""
        self.status.setText(text)
