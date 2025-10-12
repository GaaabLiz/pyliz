from PySide6.QtCore import Signal, QSize, Qt
from PySide6.QtWidgets import QWidget, QHBoxLayout, QSizePolicy
from qfluentwidgets import BodyLabel, ToolButton, FluentIcon


class FileItem(QWidget):
    """ File item """

    removed = Signal(QWidget)

    def __init__(self, file: str, parent=None):
        super().__init__(parent=parent)
        self.file = file
        self.hBoxLayout = QHBoxLayout(self)
        self.fileLabel = BodyLabel(file, self)
        self.removeButton = ToolButton(FluentIcon.CLOSE, self)

        self.removeButton.setFixedSize(39, 29)
        self.removeButton.setIconSize(QSize(12, 12))

        self.setFixedHeight(53)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.hBoxLayout.setContentsMargins(48, 0, 60, 0)
        self.hBoxLayout.addWidget(self.fileLabel, 0, Qt.AlignmentFlag.AlignLeft)
        self.hBoxLayout.addSpacing(16)
        self.hBoxLayout.addStretch(1)
        self.hBoxLayout.addWidget(self.removeButton, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.removeButton.clicked.connect(lambda: self.removed.emit(self))

