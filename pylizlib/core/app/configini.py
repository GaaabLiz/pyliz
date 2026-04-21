"""INI configuration helpers used by the application package."""

import configparser
import os
from dataclasses import dataclass
from pathlib import Path

import rich

from pylizlib.core.log.pylizLogger import logger


@dataclass(slots=True)
class IniItem:
    """Represent a single INI entry to create or update."""

    section: str
    key: str
    value: str | bool | int


class IniManager:
    """Read, create, and update INI configuration files."""

    def __init__(self, path_to_ini: str | os.PathLike[str]):
        """Store the path to the target INI file."""

        self.config: configparser.ConfigParser | None = None
        self.path = os.fspath(path_to_ini)

    def _ensure_parent_dir(self) -> None:
        """Create the parent directory for the INI file when needed."""

        parent = os.path.dirname(self.path)
        if parent:
            os.makedirs(parent, exist_ok=True)

    def exists(self) -> bool:
        """Return ``True`` when the INI file exists on disk."""

        return os.path.exists(self.path)

    def create(self, items: list[IniItem] | None = None) -> None:
        """Create the INI file and optionally write initial items."""

        self.config = configparser.ConfigParser()
        items = items or []
        list_of_sections = {item.section for item in items}

        for section in list_of_sections:
            self.config.add_section(section)

        for item in items:
            self.config.set(item.section, item.key, str(item.value))

        try:
            self._ensure_parent_dir()
            with open(self.path, "w", encoding="utf-8") as configfile:
                self.config.write(configfile)
        except OSError as exc:
            logger.error(f"Error while creating configuration file '{self.path}': {exc}")

    def read(
        self,
        section: str,
        key: str,
        is_bool: bool = False,
    ) -> str | bool | None:
        """Read a value from the INI file."""

        if not self.exists():
            logger.warning(f"INI file '{self.path}' does not exist.")
            return None

        self.config = configparser.ConfigParser()
        self.config.read(self.path, encoding="utf-8")
        if not self.config.has_section(section):
            logger.warning(f"Section '{section}' does not exist in INI file '{self.path}'.")
            return None
        if not self.config.has_option(section, key):
            logger.warning(f"Key '{key}' does not exist in section '{section}'.")
            return None
        try:
            if is_bool:
                return self.config.getboolean(section, key)
            return self.config.get(section, key)
        except (ValueError, configparser.Error) as exc:
            logger.error(f"Error while reading '{key}' from section '{section}': {exc}")
            return None

    def write(
        self,
        section: str,
        key: str,
        value: str | bool | int,
    ) -> None:
        """Write or update a value in the INI file."""

        self.config = configparser.ConfigParser()
        if self.exists():
            self.config.read(self.path, encoding="utf-8")
        if not self.config.has_section(section):
            self.config.add_section(section)
        self.config.set(section, key, str(value))
        self._ensure_parent_dir()
        with open(self.path, "w", encoding="utf-8") as configfile:
            self.config.write(configfile)


@dataclass
class CfgPath:
    """Inspect INI files stored under a directory tree."""

    path: Path

    def __check_ini(
        self,
        path: str,
        keys: bool = False,
        sections: bool = True,
    ) -> None:
        """Print sections and keys found in a single INI file."""

        config = configparser.ConfigParser()
        config.read(path, encoding="utf-8")
        if sections:
            rich.print(f"Sections in {path}:")
            for section in config.sections():
                rich.print(f"  - [magenta]{section}[/magenta]")
                if keys:
                    for option in config.options(section):
                        rich.print(f"    - [cyan]{option}[/cyan]")

    def __find_ini_files(
        self,
        directory: str,
        keys: bool = False,
        sections: bool = True,
    ) -> None:
        """Walk a directory and inspect each ``.ini`` file found."""

        for root, _, files in os.walk(directory):
            for file in files:
                if file.endswith(".ini"):
                    file_path = os.path.join(root, file)
                    try:
                        self.__check_ini(file_path, keys, sections)
                    except Exception as exc:
                        rich.print(f"[red]Error processing {file_path}[/red]: {exc}")

    def check_duplicates(self, keys: bool = False, sections: bool = True) -> None:
        """Inspect every INI file below ``path`` and print its contents."""

        self.__find_ini_files(str(self.path), keys, sections)
