import os
from enum import Enum
from typing import List

from pylizlib.os import pathutils
from pylizlib.config.cfgutils import Cfgini, CfgItem
from dataclasses import dataclass


class PylizDirFoldersTemplate(Enum):
    MODELS = "models"
    AI = "ai"
    TEMP = "temp"
    LOGS = "logs"
    RESULTS = "results"


@dataclass
class PylizDirFolder:
    key: str
    name: str
    path: str



class PylizDir:

    __path: str | None = None
    __folder_name: str | None = None
    __folders: List[PylizDirFolder] = []
    __ini: Cfgini | None = None
    __ini_path: str | None = None
    __ini_initialized = False


    def __init__(self, folder_name: str):
        """
        Constructor for PylizDir class.
        :param folder_name: Full name of the folder.
        """
        # Settaggio path
        self.__folder_name = folder_name
        self.__path: str = pathutils.get_app_home_dir(folder_name)
        # Cartella pyliz
        pathutils.check_path(self.__path, True)
        pathutils.check_path_dir(self.__path)

    def get_path(self):
        return self.__path

    # FOLDERS --------------------------------------------

    def add_folder(self, key: str, folder_name: str):
        folder_path = os.path.join(self.__path, folder_name)
        pathutils.create_path(folder_path)
        pathutils.check_path(folder_path, True)
        pathutils.check_path_dir(folder_path)
        self.__folders.append(PylizDirFolder(key, folder_name, folder_path))
        return folder_path

    def add_template_folder(self, template_key: PylizDirFoldersTemplate, name: str | None = None):
        folder_name = name if name is not None else template_key.value
        self.add_folder(template_key.value, folder_name)

    def add_all_template_folders(self):
        for template_key in PylizDirFoldersTemplate:
            self.add_template_folder(template_key)

    def add_folder_with_ini(self, key: str, folder_name: str, ini_section: str, ini_key: str):
        folder_path = self.add_folder(key, folder_name)
        self.set_ini_value(ini_section, ini_key, folder_path)

    def get_folder_path(self, key: str):
        for folder in self.__folders:
            if folder.key == key:
                return folder.path
        return None

    def get_folder_template_path(self, template_key: PylizDirFoldersTemplate, add_if_not_exist: bool = False):
        path = self.get_folder_path(template_key.value)
        if path is None and add_if_not_exist:
            return self.add_template_folder(template_key)
        else:
            return path


    def check_for_all_init(self):
        if not self.__ini.exists() or not self.__ini_initialized:
            raise Exception("PylizDirError: Configuration file not initialized or not found")

    # INI --------------------------------------------

    def create_ini(self, config_name: str, list_of_items: List[CfgItem] | None = None):
        self.__ini_path = os.path.join(self.__path, config_name)
        self.__ini = Cfgini(self.__ini_path)
        if not self.__ini.exists():
            self.__ini.create(list_of_items)
        self.__ini_initialized = True

    def get_ini_value(self, section, key, is_bool=False):
        self.check_for_all_init()
        return self.__ini.read(section, key, is_bool)

    def set_ini_value(self, section, key, value):
        self.check_for_all_init()
        self.__ini.write(section, key, value)