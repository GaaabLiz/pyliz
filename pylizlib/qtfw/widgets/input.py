from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QAction, QColor
from qfluentwidgets import (
    CaptionLabel,
    CheckableMenu,
    ComboBox,
    LineEdit,
    MenuIndicatorType,
    MessageBoxBase,
    SubtitleLabel,
)


class MultiSelectionComboBox(ComboBox):
    """
    A ComboBox that allows selecting multiple items at once
    """

    selectionChanged = Signal(list)  # Emits a list of checked ComboItem objects

    def __init__(self, parent=None):
        self._checked_indexes = []  # Track selected indices
        self._checked_items = []  # Keep selected item identity stable across list mutations
        self._selection_ready = False
        super().__init__(parent=parent)
        self._placeholderText = "Select items..."
        self._selection_ready = True
        self.setText(self._placeholderText)
        self._updateTextState(True)

    def addItem(self, *args, **kwargs):
        result = super().addItem(*args, **kwargs)
        self._sync_checked_items()
        return result

    def addItems(self, *args, **kwargs):
        result = super().addItems(*args, **kwargs)
        self._sync_checked_items()
        return result

    def insertItem(self, *args, **kwargs):
        result = super().insertItem(*args, **kwargs)
        self._sync_checked_items()
        return result

    def insertItems(self, *args, **kwargs):
        result = super().insertItems(*args, **kwargs)
        self._sync_checked_items()
        return result

    def removeItem(self, *args, **kwargs):
        result = super().removeItem(*args, **kwargs)
        self._sync_checked_items()
        return result

    def setItemText(self, *args, **kwargs):
        result = super().setItemText(*args, **kwargs)
        self._sync_checked_items()
        return result

    def clear(self):
        previous = getattr(self, "_suspend_selection_events", False)
        self._suspend_selection_events = True
        try:
            result = super().clear()
        finally:
            self._suspend_selection_events = previous
        if getattr(self, "_selection_ready", False):
            self._checked_items.clear()
            self._checked_indexes.clear()
            self._update_selection_text()
            self.selectionChanged.emit([])
        return result

    def _sync_checked_items(self):
        """Keep selections attached to their ComboItem objects after mutations."""
        if not getattr(self, "_selection_ready", False) or not hasattr(self, "items"):
            return

        previous = [(id(item), item.text) for item in self._checked_items]
        selected_ids = {id(item) for item in self._checked_items}
        self._checked_items = [item for item in self.items if id(item) in selected_ids]
        self._checked_indexes = [index for index, item in enumerate(self.items) if id(item) in selected_ids]
        current = [(id(item), item.text) for item in self._checked_items]
        self._update_selection_text()
        if current != previous and not getattr(self, "_suspend_selection_events", False):
            self.selectionChanged.emit([item.text for item in self._checked_items])

    def _update_selection_text(self):
        if self._checked_items:
            self.setText(", ".join(item.text for item in self._checked_items))
            self._updateTextState(False)
        else:
            self.setText(self._placeholderText)
            self._updateTextState(True)

    def _createComboMenu(self):
        """Create a checkable menu for multi-selection"""
        menu = CheckableMenu(title="", parent=self, indicatorType=MenuIndicatorType.CHECK)
        menu.setItemHeight(33)

        for i, item in enumerate(self.items):
            action = QAction(item.text, menu)
            action.setCheckable(True)
            action.setEnabled(item.isEnabled)
            if item.icon:
                action.setIcon(item.icon)
            action.setChecked(i in self._checked_indexes)
            action.toggled.connect(lambda checked, idx=i, act=action: self._onItemToggled(idx, act))
            menu.addAction(action)

        if menu.view.width() < self.width():
            menu.view.setMinimumWidth(self.width())
            menu.adjustSize()

        menu.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        menu.closedSignal.connect(self._onDropMenuClosed)
        return menu

    def _showComboMenu(self):
        """Override to handle multi-selection menu display"""
        if not self.items:
            return

        menu = self._createComboMenu()  # This creates our CheckableMenu with actions

        # Set menu display properties
        if menu.view.width() < self.width():
            menu.view.setMinimumWidth(self.width())
            menu.adjustSize()

        menu.setMaxVisibleItems(self.maxVisibleItems())
        menu.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        menu.closedSignal.connect(self._onDropMenuClosed)
        self.dropMenu = menu

        # Position and show the menu
        x = -menu.width() // 2 + menu.layout().contentsMargins().left() + self.width() // 2
        pd = self.mapToGlobal(QPoint(x, self.height()))
        menu.exec(pd)

    def _onItemToggled(self, index: int, action: QAction):
        """Handle item toggle events"""
        if not 0 <= index < len(self.items):
            return
        item = self.items[index]
        if action.isChecked():
            if all(selected is not item for selected in self._checked_items):
                self._checked_items.append(item)
        else:
            self._checked_items = [selected for selected in self._checked_items if selected is not item]

        self._sync_checked_items()
        self.selectionChanged.emit([selected.text for selected in self._checked_items])

    def checkedItems(self):
        """Get list of selected items"""
        return self._checked_items[:]

    def checkedIndexes(self):
        """Get list of selected indices"""
        return self._checked_indexes[:]

    def clearChecks(self):
        """Clear all selections"""
        self._checked_items.clear()
        self._checked_indexes.clear()
        self._update_selection_text()
        self.selectionChanged.emit([])

    def setCheckedIndexes(self, indexes: list[int]):
        """Set selected indices"""
        valid = sorted({i for i in indexes if 0 <= i < len(self.items)})
        self._checked_items = [self.items[index] for index in valid]
        self._sync_checked_items()
        self.selectionChanged.emit([item.text for item in self._checked_items])

    def setPlaceholderText(self, text: str):
        """Set placeholder text shown when no items are selected"""
        self._placeholderText = text
        if not self._checked_items:
            self._update_selection_text()

    def get_items(self) -> list[str]:
        items = self.checkedItems()
        return [i.text for i in items]

    def setCheckedItems(self, item_texts: list[str]):
        """Set selected items by their text values"""
        if not item_texts:
            self.clearChecks()
            return

        # Find indices of items that match the provided texts
        indexes_to_check = []
        for text in item_texts:
            for i, item in enumerate(self.items):
                if item.text == text:
                    indexes_to_check.append(i)
                    break  # Found the item, move to next text

        # Use the existing setCheckedIndexes method
        self.setCheckedIndexes(indexes_to_check)


class LineEditMessageBox(MessageBoxBase):
    """Custom message box"""

    def __init__(
        self,
        title: str,
        placeholder: str,
        text_yes: str = "Yes",
        text_no: str = "No",
        error_label: str = "Invalid.",
        parent=None,
    ):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel(title, self)
        self.line_edit = LineEdit(self)

        self.line_edit.setPlaceholderText(placeholder)
        self.line_edit.setClearButtonEnabled(True)

        self.warningLabel = CaptionLabel(error_label, parent)
        self.warningLabel.setTextColor("#cf1010", QColor(255, 28, 32))

        # add widget to view layout
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.line_edit)
        self.viewLayout.addWidget(self.warningLabel)
        self.warningLabel.hide()

        # change the text of button
        self.yesButton.setText(text_yes)
        self.cancelButton.setText(text_no)

        self.widget.setMinimumWidth(350)

        # self.hideYesButton()
