from util import osutils, pathutils
from util.loggiz import Loggiz


class Easinit:
    def __init__(
            self,
            app_name: str,
            console_log=False,
            file_log=False
    ):
        self.console_log = console_log
        self.file_log = file_log
        self.app_name = app_name
        self.home_folder_name = "." + self.app_name.lower().replace(" ", "_")
        self.setting_file_name = "config.ini"
        self.dir_app = pathutils.get_app_home_dir(self.home_folder_name)

    def create(self):
        pass

    def set_logging(self):
        Loggiz.setup(
            app_name=self.app_name,
            setup_console=False,
            file_log_base_path=self.dir_app,
            file_log_folder_name="logs",
        )

    def set_config(self):
        pass