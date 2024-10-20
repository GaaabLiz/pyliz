import os
from typing import List

from util import pathutils
from util.cfgutils import CfgItem, Cfgini


class PylizDir:
    cfgini: Cfgini = None
    path: str = None
    path_config_ini = None
    path_models: str = None
    ini_initialized = False


    @staticmethod
    def create(folder_name: str, main_config_name: str = "config.ini"):
        # Settaggio path
        PylizDir.path = pathutils.get_app_home_dir(folder_name)
        PylizDir.path_config_ini = os.path.join(PylizDir.path, main_config_name)
        # Cartella pyliz
        pathutils.check_path(PylizDir.path, True)
        pathutils.check_path_dir(PylizDir.path)
        # Cartella models
        PylizDir.path_models = os.path.join(PylizDir.path, "models")
        pathutils.check_path(PylizDir.path_models, True)
        pathutils.check_path_dir(PylizDir.path_models)
        # Cartella ai
        pathutils.check_path(PylizDir.get_ai_folder(), True)
        # Cartella logs
        pathutils.check_path(PylizDir.get_logs_path(), True)
        # File config.ini
        item_model = CfgItem("paths", "model_folder", PylizDir.path_models)
        ini_items_list: List[CfgItem] = [item_model]
        PylizDir.cfgini = Cfgini(PylizDir.path_config_ini)
        if not PylizDir.cfgini.exists():
            PylizDir.cfgini.create(ini_items_list)
        PylizDir.ini_initialized = True


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
        if not PylizDir.cfgini.exists() or not PylizDir.ini_initialized:
            raise Exception("CfgUtil object inside PylizDir not initialized.")
        PylizDir.cfgini.write(item.section, item.key, item.value)

    @staticmethod
    def get_ini_item(section: str, key: str, is_bool=False):
        if not PylizDir.cfgini.exists() or not PylizDir.ini_initialized:
            raise Exception("CfgUtil object inside PylizDir not initialized.")
        return PylizDir.cfgini.read(section, key, is_bool)
