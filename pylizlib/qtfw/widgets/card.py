from enum import Enum

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFileDialog, QWidget, QHBoxLayout
from qfluentwidgets import qconfig, Dialog, ConfigItem, FluentIcon, PushButton, ExpandSettingCard, \
    GroupHeaderCardWidget, BodyLabel
from qfluentwidgets.components.settings.folder_list_setting_card import FolderItem

from pylizlib.qtfw.domain.sw import SoftwareData
from pylizlib.qtfw.widgets.data import FileItem
from pylizlib.qtfw.widgets.input import LineEditMessageBox


class MasterListSettingCard(ExpandSettingCard):

    class Type(Enum):
        FILE = 1
        FOLDER = 2
        TEXT = 3

    item_changed = Signal(list)

    def __init__(
            self,
            config_item: ConfigItem,
            item_type: Type,
            card_title: str,
            card_icon: FluentIcon,
            card_content: str,
            main_btn: PushButton,
            dialog_title: str,
            dialog_content: str = "",
            dialog_directory="./",
            dialog_button_yes: str = "Conferma",
            dialog_button_no: str = "Annulla",
            dialog_error: str = "Errore",
            dialog_file_filter: str = "All Files (*.*)",
            deletion_title: str = "Confirm Deletion",
            deletion_content: str = "Are you sure you want to delete this item?",
            parent: QWidget = None,
    ):
        super().__init__(card_icon, card_title, card_content, parent)
        self.configItem = config_item
        self.item_type = item_type
        self.parent = parent

        # Objects
        self.dialog_title = dialog_title
        self.dialog_directory = dialog_directory
        self.dialog_content = dialog_content
        self.dialog_file_filter = dialog_file_filter
        self.dialog_button_yes = dialog_button_yes
        self.dialog_error = dialog_error
        self.dialog_button_no = dialog_button_no
        self.main_btn = main_btn
        self.items = qconfig.get(config_item).copy()
        self.title_deletion = deletion_title
        self.content_deletion = deletion_content

        # Init widgets
        self.__initWidget()


    def __initWidget(self):
        self.addWidget(self.main_btn)

        # initialize layout
        self.viewLayout.setSpacing(0)
        self.viewLayout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.viewLayout.setContentsMargins(0, 0, 0, 0)
        for item in self.items:
            self.__addItem(item)

        self.main_btn.clicked.connect(self.__show_dialog)

    def __show_dialog(self):
        success = False
        match self.item_type:
            case self.Type.FOLDER:
                folder = QFileDialog.getExistingDirectory(
                    self, self.tr(self.dialog_title), self.dialog_directory)
                if not folder or folder in self.items:
                    return
                self.__addItem(folder)
                self.items.append(folder)
                success = True
            case self.Type.FILE:
                files, _ = QFileDialog.getOpenFileNames(self, self.tr(self.dialog_title), self.dialog_directory, self.dialog_file_filter)
                for file in files:
                    if file and file not in self.items:
                        self.items.append(file)
                        self.__addItem(file)
                        success = True
            case self.Type.TEXT:
                box = LineEditMessageBox(self.dialog_title, self.dialog_content, self.dialog_button_yes, self.dialog_button_no, self.dialog_error, self.parent)
                if box.exec() == Dialog.DialogCode.Accepted:
                    text = box.line_edit.text()
                    if text and text not in self.items:
                        self.items.append(text)
                        self.__addItem(text)
                        success = True
            case _:
                raise ValueError("Invalid item type")
        if success:
            qconfig.set(self.configItem, self.items)
            self.item_changed.emit(self.items)

    def __showConfirmDialog(self, item: FolderItem | FileItem):
        """ show confirm dialog """
        w = Dialog(self.title_deletion, self.content_deletion, self.window())
        w.yesSignal.connect(lambda: self.__remove_item(item))
        w.exec_()

    def __addItem(self, data: str):
        match self.item_type:
            case self.Type.FOLDER:
                item = FileItem(data, self.view)
            case self.Type.FILE:
                item = FileItem(data, self.view)
            case self.Type.TEXT:
                item = FileItem(data, self.view)
            case _:
                raise ValueError("Invalid item type")
        item.removed.connect(self.__showConfirmDialog)
        self.viewLayout.addWidget(item)
        item.show()
        self._adjustViewSize()

    def __remove_item(self, item: FolderItem | FileItem):
        match self.item_type:
            case self.Type.FOLDER:
                if item.folder not in self.items:
                    return
                self.items.remove(item.folder)
            case self.Type.FILE | self.Type.TEXT:
                if item.file not in self.items:
                    return
                self.items.remove(item.file)
            case _:
                raise ValueError("Invalid item type")
        self.viewLayout.removeWidget(item)
        item.deleteLater()
        self._adjustViewSize()
        qconfig.set(self.configItem, self.items)
        self.item_changed.emit(self.items)


class SoftwareListStatusGroupCard(GroupHeaderCardWidget):

    class SoftwareDataWidget(QWidget):

        def __init__(self, parent: QWidget, data: SoftwareData):
            super().__init__(parent)
            self.data = data

            self.label_installed = BodyLabel( self)
            self.label_running = BodyLabel(self)
            self.label_version = BodyLabel(self)

            self.label_version.setToolTip("Versione di " + self.data.path.name)

            layout = QHBoxLayout(self)
            layout.addWidget(self.label_installed, 0, Qt.AlignmentFlag.AlignRight)
            layout.addWidget(self.label_running, 0, Qt.AlignmentFlag.AlignRight)
            layout.addWidget(self.label_version, 0, Qt.AlignmentFlag.AlignRight)

        def update_data(self):
            self.label_version.setText(self.data.version)

            if self.data.installed:
                self.label_installed.setText("✅")
                self.label_installed.setToolTip("Installato")
            else:
                self.label_installed.setText("🚫")
                self.label_installed.setToolTip("Non trovato")

            if self.data.running:
                self.label_running.setText("🟢")
                self.label_running.setToolTip("In esecuzione")
            else:
                self.label_running.setText("🔴")
                self.label_running.setToolTip("Non in esecuzione")

    def __init__(self, title:str, parent=None):
        super().__init__(parent)
        self.setTitle(title)
        self.setBorderRadius(8)
        self.software_data: list[SoftwareData] = []
        self.groups = {}

    def add_software_data(self, data: SoftwareData):
        widget = SoftwareListStatusGroupCard.SoftwareDataWidget(self, data)
        self.addGroup(data.icon, data.path.name, data.path.__str__(), widget)
        self.groups[data.path.name] = widget
        self.software_data.append(data)

    def update_all(self):
        for data in self.software_data:
            self.groups[data.path.name].update_data()

    def clear_all_data(self):
        # Rimuove tutti i widget dei gruppi salvati e pulisce la struttura dati
        for group_name, widget in self.groups.items():
            # Rimuove il widget dal layout o dal QWidget principale
            widget.setParent(None)
            widget.deleteLater()
        self.groups.clear()
        self.software_data.clear()