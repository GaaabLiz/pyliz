from pylizlib.config.pylizapp import PylizApp
from pylizlib.domain.config import ConfigItem


class ConfigHandler:

    @staticmethod
    def read(
            item: ConfigItem,
            use_default_if_none: bool = False,
            use_empty_if_none: bool = False,
            app: PylizApp = PylizApp("PylizNull"),
    ) -> str | bool | None:
        result = app.get_ini_value(item.section, item.id, item.is_bool)
        if result is None:
            if item.default is not None and use_default_if_none:
                ConfigHandler.write(item, item.default, app)
                return item.default
            if use_empty_if_none:
                return ""
            return None
        else:
            return result

    @staticmethod
    def write(item: ConfigItem, value: str | bool | None = None, app: PylizApp = PylizApp("PylizNull")) -> None:
        if value is None:
            if item.default is not None:
                value = item.default
            else:
                raise ValueError("Value cannot be None and no default value is set.")
        app.set_ini_value(item.section, item.id, value)

    @staticmethod
    def safe_int_read(item: ConfigItem) -> int:
        try:
            result = int(ConfigHandler.read(item))
            return result
        except ValueError:
            # Log the error or handle it as needed
            return item.default if item.default is not None else 0