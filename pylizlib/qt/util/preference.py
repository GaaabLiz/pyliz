from typing import Any, Callable

from PySide6.QtWidgets import QGroupBox, QFormLayout, QSizePolicy

from pylizlib.core.app.pylizapp import PylizApp
from pylizlib.qt.domain.preference import PreferenceConfigData, PreferenceTypes


# def create_prf_path(item: ConfigIniItem, app: PylizApp) -> PreferenceItemPath:
#     return PreferenceItemPath(
#         label=QLabel(item.name),
#         widget=PathLineSelector(),
#         config_id=item.id,
#         getter=lambda: ConfigHandler.read(item, app=app),
#         setter=lambda value: ConfigHandler.write(item, value, app=app),
#     )
#
#
# def create_prf_checkbox(item: ConfigItem, app: PylizApp) -> PreferenceItemCheck:
#     widget = QCheckBox()
#     return PreferenceItemCheck(
#         label=QLabel(item.name),
#         widget=widget,
#         config_id=item.id,
#         getter=lambda: ConfigHandler.read(item, app=app),
#         setter=lambda value: ConfigHandler.write(item, value, app=app),
#     )
#
#
# def create_prf_combo_box(item: ConfigItem, app: PylizApp) -> PreferenceItemCombo:
#     widget = QComboBox()
#     for value in item.values:
#         widget.addItem(value)
#     return PreferenceItemCombo(
#         label=QLabel(item.name),
#         widget=widget,
#         config_id=item.id,
#         getter=lambda: ConfigHandler.read(item, app=app),
#         setter=lambda value: ConfigHandler.write(item, value, app=app),
#     )
#
#
# def create_prf_spin_box(item: ConfigItem, app: PylizApp) -> PreferenceItemSpinBox:
#     widget = QSpinBox()
#     widget.setMinimum(int(item.min_value))
#     widget.setMaximum(int(item.max_value))
#     widget.setSingleStep(1)
#     return PreferenceItemSpinBox(
#         label=QLabel(item.name),
#         widget=widget,
#         config_id=item.id,
#         getter=lambda: int(ConfigHandler.read(item, app=app)),
#         setter=lambda value: ConfigHandler.write(item, str(value), app=app),
#     )


def create_prf_group_box_form_layout(name: str, parent: Any) -> tuple:
    group_box = QGroupBox(name, parent)
    group_box.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
    form_layout = QFormLayout(group_box)
    form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
    group_box.setLayout(form_layout)
    return group_box, form_layout


# def add_ui_to_form_layout(
#         data: PreferenceConfigData,
#         layout: QFormLayout,
#         app: PylizApp,
#         on_change: Callable[[ConfigIniItem, str | None, bool | None], None],
# ) -> None:
#     match data.type:
#         case PreferenceTypes.PATH:
#             element = create_prf_path(data.config, app)
#             element.widget.setText(element.getter())
#             element.widget.get_text_changed().connect(element.setter)
#             element.widget.get_text_changed().connect(lambda text: on_change(data.config, text, None))
#             layout.addRow(element.label, element.widget)
#         case PreferenceTypes.CHECK:
#             element = create_prf_checkbox(data.config, app)
#             element.widget.setChecked(element.getter())
#             element.widget.stateChanged.connect(lambda state: element.setter(bool(state)))
#             element.widget.stateChanged.connect(lambda state: on_change(data.config, None, bool(state)))
#             layout.addRow(element.label, element.widget)
#             pass
#         case PreferenceTypes.COMBO:
#             element = create_prf_combo_box(data.config, app)
#             element.widget.setCurrentText(element.getter())
#             element.widget.currentTextChanged.connect(element.setter)
#             element.widget.currentTextChanged.connect(lambda text: on_change(data.config, text, None))
#             layout.addRow(element.label, element.widget)
#         case PreferenceTypes.SPINBOX:
#             element = create_prf_spin_box(data.config, app)
#             element.widget.setValue(element.getter())
#             element.widget.valueChanged.connect(element.setter)
#             element.widget.valueChanged.connect(lambda value: on_change(data.config, str(value), None))
#             layout.addRow(element.label, element.widget)