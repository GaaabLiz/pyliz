import os

from util import pathutils
from util.cfgutils import CfgItem, Cfgini


class PylizDir:

    base_path: str = pathutils.get_app_home_dir(".pyliz")

    @staticmethod
    def create():
        exist = pathutils.check_path(PylizDir.base_path, True)
        if exist:
            return
        pathutils.check_path_dir(PylizDir.base_path)

    @staticmethod
    def set_default():
        # Creating variables
        path_config_ini = os.path.join(PylizDir.base_path, "config.ini")
        path_models_folder = os.path.join(PylizDir.base_path, "models")
        ini_items_list = [
            CfgItem("paths", "model_folder", path_models_folder)
        ]
        # Checking variables
        pathutils.check_path(path_models_folder, True)
        pathutils.check_path_dir(path_models_folder)
        # Creating config.ini file
        cfgini = Cfgini(path_config_ini)
        cfgini.create(ini_items_list)


    def check_models_folder(self):
        path = os.path.join(self.base_path, "models")
        pathutils.check_path(path, True)
        pathutils.check_path_dir(path)
