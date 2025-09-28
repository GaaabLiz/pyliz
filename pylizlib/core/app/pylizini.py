from dataclasses import dataclass

from pylizlib.core.app.pylizapp import PylizApp


@dataclass
class PylizIniItem:
    id: str
    name: str
    section: str
    is_bool: bool = False
    default: int | str | bool | None = None
    values: list[str] | None = None
    min_value: str | None = None
    max_value: str | None = None
    require_reboot: bool = False


class PylizIniHandler:

    @staticmethod
    def read(
            item: PylizIniItem,
            use_default_if_none: bool = False,
            use_empty_if_none: bool = False,
            app: PylizApp = PylizApp("PylizNull"),
    ) -> str | bool | None:
        result = app.get_ini_value(item.section, item.id, item.is_bool)
        if result is None:
            if item.default is not None and use_default_if_none:
                PylizIniHandler.write(item, item.default, app)
                return item.default
            if use_empty_if_none:
                return ""
            return None
        else:
            return result

    @staticmethod
    def write(item: PylizIniItem, value: str | bool | None = None, app: PylizApp = PylizApp("PylizNull")) -> None:
        if value is None:
            if item.default is not None:
                value = item.default
            else:
                raise ValueError("Value cannot be None and no default value is set.")
        app.set_ini_value(item.section, item.id, value)

    @staticmethod
    def safe_int_read(item: PylizIniItem) -> int:
        try:
            result = int(PylizIniHandler.read(item))
            return result
        except ValueError:
            # Log the error or handle it as needed
            return item.default if item.default is not None else 0
