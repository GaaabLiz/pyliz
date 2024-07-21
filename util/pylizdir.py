import os

from util import pathutils
from util.cfgutils import CfgItem, Cfgini


class PylizDir:

    path: str = pathutils.get_app_home_dir(".pyliz")
    path_config_ini = os.path.join(path, "config.ini")

    default_path_models: str = os.path.join(path, "models")

    ini_items_list = [
        CfgItem("paths", "model_folder", default_path_models)
    ]

    @staticmethod
    def create():
        # Cartella pyliz
        pathutils.check_path(PylizDir.path, True)
        pathutils.check_path_dir(PylizDir.path)
        # File config.ini
        cfgini = Cfgini(PylizDir.path_config_ini)
        if not cfgini.exists():
            cfgini.create(PylizDir.ini_items_list)
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
