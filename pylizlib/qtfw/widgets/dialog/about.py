from PySide6.QtGui import QAction, QColor, QIcon
from PySide6.QtWidgets import QFileDialog, QWidget, QSizePolicy, QHBoxLayout, QApplication, QFrame, QLabel, QVBoxLayout
from PySide6.QtCore import Qt, Signal, QSize, QPoint
from qfluentwidgets import ExpandSettingCard, ConfigItem, PushButton, qconfig, Dialog, ToolButton, BodyLabel, \
    GroupHeaderCardWidget, ComboBox, \
    FluentIcon, \
    CheckableMenu, MenuIndicatorType, MessageBoxBase, SubtitleLabel, LineEdit, CaptionLabel, Theme, isDarkTheme

class AboutMessageBox(MessageBoxBase):
    def __init__(
            self,
            icon: QIcon,
            app_name: str,
            app_version: str,
            parent=None
    ):
        super().__init__(parent)

        # Logo (icona) - usa QLabel con pixmap
        self.logoLabel = QLabel(self)
        self.logoLabel.setPixmap(icon.pixmap(64, 64))
        self.logoLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Nome app grande
        self.appNameLabel = SubtitleLabel(app_name, self)
        self.appNameLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Versione app
        self.versionLabel = CaptionLabel("Versione " + app_version, self)
        self.versionLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Layout orizzontale per logo a sinistra e testo a destra
        topLayout = QHBoxLayout()
        topLayout.addWidget(self.logoLabel)
        textLayout = QHBoxLayout()
        textLayout.addWidget(self.appNameLabel)
        topLayout.addLayout(textLayout)

        # Aggiungo layout con logo e nome
        self.viewLayout.addLayout(topLayout)
        self.viewLayout.addWidget(self.versionLabel)

        # Setto dimensione minima
        self.widget.setMinimumWidth(350)

        # Cambia testo pulsanti se vuoi
        self.yesButton.setText("Close")
        self.cancelButton.hide()  # Nascondi cancella se serve

    def validate(self):
        # Per about box non serve validazione, sempre true
        return True