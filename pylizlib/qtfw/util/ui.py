from functools import partial
from pathlib import Path
from typing import Any

from qfluentwidgets import SubtitleLabel, setFont, TransparentDropDownPushButton, DropDownPushButton, RoundMenu, \
    Dialog, FluentIcon, Action


class UiUtils:

    @staticmethod
    def show_message(title, text: str, parent=None):
        w = Dialog(title, text, parent)
        w.cancelButton.hide()
        w.buttonLayout.insertStretch(1)
        w.exec()

    @staticmethod
    def create_widget_act_bar_btn(
            parent: Any,
            data: list[str] | list[Path],
            btn_name: str,
            icon: FluentIcon,
            is_trasparent: bool = True,
            clicked_signal=None,
            icon_action: FluentIcon | None = None
    ):
        actions: list[Action] = []
        for action_text in data:
            if isinstance(action_text, Path):
                action_text = action_text.__str__()
            act = Action(icon if icon_action is None else icon_action, action_text, parent)
            if clicked_signal is not None:
                act.triggered.connect(partial(clicked_signal.emit, action_text))
            actions.append(act)

        if is_trasparent:
            button = TransparentDropDownPushButton(btn_name, parent, icon)
        else:
            button = DropDownPushButton(btn_name, parent, icon)
        button.setFixedHeight(34)
        setFont(button, 12)

        menu = RoundMenu(parent=parent)
        for act in actions:
            menu.addAction(act)
        button.setMenu(menu)

        return button