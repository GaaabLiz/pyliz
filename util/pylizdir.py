import os
from typing import List

from util import pathutils
from util.cfgutils import CfgItem, Cfgini


class PylizDir:
    cfgini: Cfgini = None
    path: str = None
    path_config_ini = os.path.join(path, "config.ini")

    default_path_models: str = os.path.join(path, "models")

    ini_items_list = [
        CfgItem("paths", "model_folder", default_path_models)
    ]

    @staticmethod
    def create(folder_name: str):
        # Settaggio path
        PylizDir.path = pathutils.get_app_home_dir(folder_name)
        # Cartella pyliz
        pathutils.check_path(PylizDir.path, True)
        pathutils.check_path_dir(PylizDir.path)
        # File config.ini
        PylizDir.cfgini = Cfgini(PylizDir.path_config_ini)
        if not PylizDir.cfgini.exists():
            PylizDir.cfgini.create(PylizDir.ini_items_list)
        # Cartella models
        pathutils.check_path(PylizDir.default_path_models, True)
        pathutils.check_path_dir(PylizDir.default_path_models)
        # Cartella ai
        pathutils.check_path(PylizDir.get_ai_folder(), True)
        # Cartella logs
        pathutils.check_path(PylizDir.get_logs_path(), True)


    @staticmethod
    def get_models_folder() -> str:
        cfgini = Cfgini(PylizDir.path_config_ini)
        path = cfgini.read("paths", "model_folder")
        pathutils.check_path(path, True)
        return path

    @staticmethod
    def get_ai_folder() -> str:
        path = os.path.join(PylizDir.path, "ai")
        pathutils.check_path(path, True)
        return path

    @staticmethod
    def get_logs_path() -> str:
        path = os.path.join(PylizDir.path, "logs")
        pathutils.check_path(path, True)
        return path

    @staticmethod
    def set_ini_item(item: CfgItem):
        PylizDir.cfgini.write(item.section, item.key, item.value)

    @staticmethod
    def get_ini_item(section: str, key: str, is_bool=False):
        return PylizDir.cfgini.read(section, key, is_bool)
