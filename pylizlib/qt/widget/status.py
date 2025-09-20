from PySide6.QtWidgets import QStatusBar, QProgressBar


class QtLizStatusBar(QStatusBar):

    def __init__(self, parent):
        super().__init__(parent)
        self.showMessage("Ready")
        self.progress_bar = None
        self.__setup_status_bar()

    def __setup_status_bar(self):
        self.showMessage("Ready")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        self.addPermanentWidget(self.progress_bar)

    def update_progress_bar(self, value: int):
        self.progress_bar.setValue(value)
        if value == 100:
            self.progress_bar.setVisible(False)
        else:
            self.progress_bar.setVisible(True)

    def set_status_message(self, message: str):
        self.showMessage(message)