import os

from util import pathutils
from util.cfgutils import CfgItem, Cfgini


class PylizDir:

    path: str = pathutils.get_app_home_dir(".pyliz")
    path_config_ini = os.path.join(path, "config.ini")

    default_path_models: str = os.path.join(path, "models")

    @staticmethod
    def create():
        exist = pathutils.check_path(PylizDir.path, True)
        if exist:
            return
        pathutils.check_path_dir(PylizDir.path)

    @staticmethod
    def set_default():
        # Creating variables
        ini_items_list = [
            CfgItem("paths", "model_folder", PylizDir.default_path_models)
        ]
        # Checking variables
        pathutils.check_path(PylizDir.default_path_models, True)
        pathutils.check_path_dir(PylizDir.default_path_models)
        # Creating config.ini file
        cfgini = Cfgini(PylizDir.path_config_ini)
        cfgini.create(ini_items_list)

    @staticmethod
    def get_models_folder() -> str:
        cfgini = Cfgini(PylizDir.path_config_ini)
        return cfgini.read("paths", "model_folder")

    @staticmethod
    def get_ai_folder() -> str:
        path = os.path.join(PylizDir.path, "ai")
        pathutils.check_path(path, True)
        return path
