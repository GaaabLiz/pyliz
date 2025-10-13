from dataclasses import dataclass
from typing import List, Callable, Optional

from PySide6.QtCore import Signal, QThread, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QDialog, QVBoxLayout
from qfluentwidgets import BodyLabel, ProgressBar, FluentStyleSheet

from pylizlib.core.log.pylizLogger import logger


@dataclass
class SimpleProgressSettings:
    status_text_each_prefix: str = "Operazione "
    status_text_each_suffix: str = "di "
    completed_text_prefix: str = "Operazione completata"
    completed_text_suffix: str = ""
    window_title: str = "Operazione in corso"
    window_height: int = 150
    window_width: int = 350
    window_label: str = "Aggiornamento in corso..."
    initial_status_text: str = "Preparazione..."


    def get_status_text(self, current: int, total: int) -> str:
        return f"{self.status_text_each_prefix}{current}{self.status_text_each_suffix}{total}"

    def get_completed_text(self, text: str) -> str:
        return f"{self.completed_text_prefix} {text}{self.completed_text_suffix}"



class SimpleProgressWorker(QThread):
    """Worker thread semplice per operazioni in background"""

    progress_updated = Signal(int, str)  # progress, status
    finished_signal = Signal(bool)      # success
    started_signal = Signal(int)        # max_value
    operation_status_updated = Signal(str)  # status_text from operation


    def __init__(self, operations: List[Callable], settings: SimpleProgressSettings = SimpleProgressSettings()):
        super().__init__()
        self.exception = None
        self.operations = operations
        self.settings = settings

    def run(self):
        try:
            total = len(self.operations)
            self.started_signal.emit(total)

            for i, operation in enumerate(self.operations):
                status = self.settings.get_status_text(i+1, total)
                self.progress_updated.emit(i, status)

                # Esegui l'operazione passando la callback per gli aggiornamenti di stato
                if hasattr(operation, '__call__'):
                    # Controlla se l'operazione accetta un parametro (la callback)
                    import inspect
                    sig = inspect.signature(operation)
                    if len(sig.parameters) > 0:
                        # Passa la callback che emette il segnale
                        operation(lambda msg: self.operation_status_updated.emit(msg))
                    else:
                        operation()
                else:
                    operation()

                # Aggiorna il progresso dopo l'operazione
                self.progress_updated.emit(i+1, self.settings.get_completed_text(f"{i+1}/{total}"))
                self.msleep(100)

            self.finished_signal.emit(True)
        except Exception as e:
            logger.error(f"Error: {e}")
            self.exception = e
            self.finished_signal.emit(False)


class SimpleProgressDialog(QDialog):
    """Dialog semplice con progress bar"""

    def __init__(self, parent=None, settings: SimpleProgressSettings = SimpleProgressSettings()):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle(self.settings.window_title)
        self.setFixedSize(self.settings.window_width, self.settings.window_height)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowTitleHint)  # Non chiudibile
        self.setModal(True)

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

    def closeEvent(self, event):
        event.ignore()  # Impedisce chiusura

    def update_status_only(self, text: str):
        """Aggiorna solo il testo di stato senza cambiare il progresso"""
        self.status.setText(text)



class SimpleProgressManager:
    """Manager semplificato per progress dialog"""

    def __init__(self, parent=None, settings: SimpleProgressSettings = SimpleProgressSettings()):
        self.settings = settings
        self.parent = parent
        self.worker = None
        self.dialog = None

    def start_operations(self, operations: List[Callable],
                         callback: Optional[Callable] = None):
        """Avvia operazioni con progress dialog"""

        # Crea dialog
        self.dialog = SimpleProgressDialog(self.parent, self.settings)

        # Crea worker
        self.worker = SimpleProgressWorker(operations, self.settings)

        # Connetti segnali
        self.worker.started_signal.connect(self.dialog.set_maximum)
        self.worker.progress_updated.connect(self.dialog.update_progress)
        self.worker.operation_status_updated.connect(self.dialog.update_status_only)  # NUOVO
        self.worker.finished_signal.connect(
            lambda success: self._on_finished(success, callback)
        )

        # Mostra dialog e avvia worker
        self.dialog.show()
        self.worker.start()

    def _on_finished(self, success: bool, callback: Optional[Callable]):
        """Gestisce il completamento"""
        # Salva l'eccezione prima di pulire
        exception_to_raise = None
        if not success and self.worker and hasattr(self.worker, 'exception'):
            exception_to_raise = self.worker.exception

        # Chiudi dialog
        if self.dialog:
            self.dialog.accept()
            self.dialog = None

        # Aspetta che il thread finisca
        if self.worker:
            self.worker.wait()
            self.worker = None

        # Callback con l'eccezione se presente
        if callback:
            if exception_to_raise:
                callback(success, exception_to_raise)  # Passa anche l'eccezione
            else:
                callback(success, None)

        # Messaggio finale solo se successo e nessun callback personalizzato
        elif success:
            pass
            from PySide6.QtWidgets import QMessageBox
            #QMessageBox.information(self.parent_widget, "Completato",
                                    # "Operazioni completate con successo!")
        # Messaggio finale
        # from PySide6.QtWidgets import QMessageBox
        # if success:
        #     QMessageBox.information(self.parent, "Completato",
        #                             "Operazioni completate con successo!")
        # else:
        #     QMessageBox.warning(self.parent, "Errore",
        #                         "Si Ã¨ verificato un errore!")



