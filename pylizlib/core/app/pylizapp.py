"""Application helpers for local folders and INI configuration files."""

import os
from dataclasses import dataclass
from enum import Enum

from pylizlib.core.app.configini import IniItem, IniManager
from pylizlib.core.log.pylizLogger import logger
from pylizlib.core.os import path as pathutils


class PylizDirFoldersTemplate(Enum):
    """Standard folder names used by :class:`PylizApp`."""

    MODELS = "models"
    AI = "ai"
    TEMP = "temp"
    LOGS = "logs"
    RESULTS = "results"


@dataclass
class PylizDirFolder:
    """Store folder metadata tracked by :class:`PylizApp`."""

    key: str
    name: str
    path: str


class PylizApp:
    """Manage an application home directory and its configuration file."""

    language_version: str | None = None

    def __init__(
        self,
        app_name: str,
        app_version: str | None = None,
        folder_name: str | None = None,
        author: str = "Unknown",
    ):
        """Initialize the application home directory.

        :param app_name: Public application name.
        :param app_version: Optional application version.
        :param folder_name: Optional custom directory name under the user home.
        :param author: Application author name.
        """
        app_folder_name = folder_name if folder_name is not None else app_name
        self.path: str = pathutils.get_app_home_dir(app_folder_name)
        pathutils.check_path(self.path, True)
        pathutils.check_path_dir(self.path)
        self.name = app_name
        self.version = app_version
        self.author = author
        self.__folders: list[PylizDirFolder] = []
        self.__ini: IniManager | None = None
        self.__ini_path: str | None = None
        self.__ini_initialized = False

    def get_path(self) -> str:
        """Return the application home directory path."""

        return self.path

    def _get_folder_index(self, key: str) -> int | None:
        """Return the index of a tracked folder by key, if present."""

        for index, folder in enumerate(self.__folders):
            if folder.key == key:
                return index
        return None

    def add_folder(self, key: str, folder_name: str) -> str:
        """Create or update a tracked subfolder inside the app directory."""

        folder_path = os.path.join(self.path, folder_name)
        pathutils.create_path(folder_path)
        pathutils.check_path(folder_path, True)
        pathutils.check_path_dir(folder_path)

        folder = PylizDirFolder(key, folder_name, folder_path)
        existing_index = self._get_folder_index(key)
        if existing_index is None:
            self.__folders.append(folder)
        else:
            self.__folders[existing_index] = folder

        return folder_path

    def add_template_folder(
        self,
        template_key: PylizDirFoldersTemplate,
        name: str | None = None,
    ) -> str:
        """Create or update a standard template folder."""

        folder_name = name if name is not None else template_key.value
        return self.add_folder(template_key.value, folder_name)

    def add_all_template_folders(self) -> list[str]:
        """Create every standard folder template and return their paths."""

        created_paths: list[str] = []
        for template_key in PylizDirFoldersTemplate:
            created_paths.append(self.add_template_folder(template_key))
        return created_paths

    def add_folder_with_ini(
        self,
        key: str,
        folder_name: str,
        ini_section: str,
        ini_key: str,
    ) -> str:
        """Create a folder and store its path inside the active INI file."""

        folder_path = self.add_folder(key, folder_name)
        self.set_ini_value(ini_section, ini_key, folder_path)
        return folder_path

    def get_folder_path(self, key: str) -> str | None:
        """Return the tracked folder path for a given key."""

        for folder in self.__folders:
            if folder.key == key:
                return folder.path
        return None

    def get_folder_template_path(
        self,
        template_key: PylizDirFoldersTemplate,
        add_if_not_exist: bool = True,
    ) -> str | None:
        """Return a template folder path and optionally create it if missing."""

        folder_path = self.get_folder_path(template_key.value)
        if folder_path is None and add_if_not_exist:
            return self.add_template_folder(template_key)
        return folder_path

    def check_for_all_init(self) -> None:
        """Validate that the INI manager is ready and the file exists."""

        if self.__ini is None or self.__ini_path is None or not self.__ini_initialized:
            raise RuntimeError("PylizApp configuration file is not initialized.")
        if not self.__ini.exists():
            raise RuntimeError("PylizApp configuration file does not exist.")

    def create_ini(self, config_name: str, list_of_items: list[IniItem] | None = None) -> str:
        """Create or load the application INI file."""

        self.__ini_path = os.path.join(self.path, config_name)
        self.__ini = IniManager(self.__ini_path)
        if not self.__ini.exists():
            self.__ini.create(list_of_items)
        self.__ini_initialized = True
        return self.__ini_path

    def get_ini_value(
        self,
        section: str,
        key: str,
        is_bool: bool = False,
    ) -> str | bool | None:
        """Read a value from the active INI file."""

        self.check_for_all_init()
        return self.__ini.read(section, key, is_bool)

    def set_ini_value(
        self,
        section: str,
        key: str,
        value: str | bool | int,
    ) -> None:
        """Write a value to the active INI file."""

        self.check_for_all_init()
        self.__ini.write(section, key, value)

    def get_ini_path(self) -> str | None:
        """Return the current INI path when the configuration is initialized."""

        if self.__ini_initialized:
            return self.__ini_path
        return None

    def delete_ini(self) -> None:
        """Delete the active INI file and reset the internal state."""

        if (
            self.__ini_initialized
            and self.__ini_path is not None
            and os.path.exists(self.__ini_path)
        ):
            os.remove(self.__ini_path)
            self.__ini_initialized = False
            self.__ini = None
            self.__ini_path = None
        else:
            logger.warning("INI file is not initialized. Nothing to delete.")

    def print_hw(self) -> None:
        """Print a simple hello-world message."""

        print("Hello from PylizApp!")
