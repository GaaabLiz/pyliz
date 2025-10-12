from qfluentwidgets import BodyLabel


class BoldLabel(BodyLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        font = self.font()
        font.setBold(True)
        self.setFont(font)

    def setText(self, text):
        super().setText(text)