"""High-level helpers for reading and writing Pyliz INI values."""

from dataclasses import dataclass

from pylizlib.core.app.pylizapp import PylizApp


@dataclass
class PylizIniItem:
    """Describe one configuration entry handled by :class:`PylizIniHandler`."""

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
    """Read and write configuration values using a :class:`PylizApp` instance."""

    @staticmethod
    def _require_app(app: PylizApp | None) -> PylizApp:
        """Return a valid app instance or raise a clear error."""

        if app is None:
            raise ValueError("A PylizApp instance is required for INI operations.")
        return app

    @staticmethod
    def read(
        item: PylizIniItem,
        use_default_if_none: bool = False,
        use_empty_if_none: bool = False,
        app: PylizApp | None = None,
    ) -> str | bool | None:
        """Read a configuration value."""

        target_app = PylizIniHandler._require_app(app)
        result = target_app.get_ini_value(item.section, item.id, item.is_bool)
        if result is None:
            if item.default is not None and use_default_if_none:
                PylizIniHandler.write(item, item.default, app=target_app)
                return item.default
            if use_empty_if_none:
                return ""
            return None
        return result

    @staticmethod
    def write(
        item: PylizIniItem,
        value: str | bool | int | None = None,
        app: PylizApp | None = None,
    ) -> None:
        """Write a configuration value."""

        target_app = PylizIniHandler._require_app(app)
        if value is None:
            if item.default is not None:
                value = item.default
            else:
                raise ValueError("Value cannot be None and no default value is set.")
        target_app.set_ini_value(item.section, item.id, value)

    @staticmethod
    def safe_int_read(item: PylizIniItem, app: PylizApp | None = None) -> int:
        """Read a configuration value as an integer with a safe fallback."""

        try:
            result = PylizIniHandler.read(item, use_default_if_none=True, app=app)
            if result is None:
                raise TypeError("Configuration value is missing.")
            return int(result)
        except (TypeError, ValueError):
            if item.default is not None:
                try:
                    return int(item.default)
                except (TypeError, ValueError):
                    return 0
            return 0
