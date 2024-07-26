import os
import subprocess
from typing import Callable

from git import Repo

from ai.core.ai_method import AiMethod
from ai.core.ai_models import AiModels
from ai.core.ai_power import AiPower
from ai.core.ai_source import AiSource
from ai.core.ai_source_type import AiSourceType
from model.operation import Operation
from util import pathutils, osutils, fileutils, datautils


# noinspection PyMethodMayBeStatic
class LlamaCpp:

    GITHUB_URL = "https://github.com/ggerganov/llama.cpp.git"

    def __init__(
            self,
            # path_install: str = os.path.join(PylizDir.get_ai_folder(), "llama.cpp"),
            # path_models: str = PylizDir.get_models_folder(),
            # path_logs: str = os.path.join(PylizDir.get_logs_path(), "llama.cpp")
            path_install: str,
            path_models: str,
            path_logs: str
    ):
        # Init paths
        self.path_install = path_install
        self.path_models = path_models
        self.path_logs = path_logs
        self.log_build_folder = os.path.join(self.path_logs, "build")
        pathutils.check_path(self.log_build_folder, True)


    def __clone_repo(self, on_log: Callable[[str], None] = lambda x: None):
        on_log("Cloning LlamaCpp...")
        # check if the folder already exists
        if os.path.exists(self.path_install):
            on_log("LlamaCpp already installed.")
            return
        else:
            on_log("LlamaCpp not installed. Proceeding...")
            pathutils.check_path(self.path_install, True)
        # checking folder
        pathutils.check_path_dir(self.path_install)
        # Cloning github repo
        Repo.clone_from(LlamaCpp.GITHUB_URL, self.path_install)
        on_log("Clone successful.")


    def __check_requirements(self, on_log: Callable[[str], None] = lambda x: None):
        on_log("Checking requirements...")
        make_ok = osutils.is_command_available("make")
        is_os_unix = osutils.is_os_unix()
        if not make_ok:
            raise Exception("Make command not available. Please install make.")
        if not is_os_unix:
            raise Exception("This component (LlamaCPP) is only available on Unix systems.")


    def __build_sources(self, on_log: Callable[[str], None] = lambda x: None):
        on_log("Building sources...")
        risultato = subprocess.run(["make"], check=True, cwd=self.path_install, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        on_log("Build successful.")
        return risultato


    def __crete_build_log(self, risultato, ):
        log_build_name = datautils.gen_timestamp_log_name("llamacpp-", ".txt")
        log_build_path = os.path.join(self.log_build_folder, log_build_name)
        with open(log_build_path, "w") as f:
            f.write(risultato.stdout)
            f.write("***********************************\n")
            f.write(risultato.stderr)

    def __download_llava_local_models(
            self,
            source: AiSource,
            folder: str,
            on_log: Callable[[str], None] = lambda x: None,
            on_progress: Callable[[int], None] = lambda x: None
    ):
        on_log("LLava require " + str(len(source.hg_files)) + " files to download.")
        for hg_file in source.hg_files:
            current_file = os.path.join(folder, hg_file.file_name)
            already_exist = os.path.exists(current_file)
            if already_exist:
                on_log("Model " + hg_file.file_name + " already installed.")
                continue
            on_log("Downloading model " + hg_file.file_name + " from Huggingface...")
            op = fileutils.download_file(hg_file.url, current_file, on_progress)
            if op.status is False:
                raise Exception("Error downloading model: " + op.error)


    def clone_and_build(self, on_log: Callable[[str], None] = lambda x: None):
        self.__clone_repo(on_log)
        self.__check_requirements(on_log)
        build = self.__build_sources(on_log)
        self.__crete_build_log(build)


    def install_llava(
            self,
            power: AiPower,
            on_log: Callable[[str], None] = lambda x: None,
            on_progress: Callable[[int], None] = lambda x: None
    ):
        self.clone_and_build(on_log)
        on_log("Installing LLava...")
        # creating and checking files/folders
        source = AiModels.Llava.get_llava(power, AiSourceType.LOCAL_LLAMACPP)
        folder = os.path.join(self.path_models, source.local_name)
        pathutils.check_path(folder, True)
        pathutils.check_path_dir(folder)
        # Checking available space
        models_size = source.get_files_size_mb()
        has_space = osutils.has_disk_free_space(folder, models_size)
        if not has_space:
            raise Exception("Not enough free space to install LLava.")
        # Downloading files
        self.__download_llava_local_models(source, folder, on_log, on_progress)
        on_log("LLava model installed.")

    def run_llava(
            self,
            power: AiPower,
            image_path: str,
            prompt: str,
    ) -> Operation[str]:
        try:
            # Creating variables and checking requirements
            source = AiModels.Llava.get_llava(power, AiSourceType.LOCAL_LLAMACPP)
            folder = os.path.join(self.path_models, source.local_name)
            if not os.path.exists(folder):
                raise Exception("LLava model not installed.")
            # Run the model
            path_model_file = os.path.join(self.path_models, source.local_name, source.get_ggml_file().file_name)
            path_mmproj_file = os.path.join(self.path_models, source.local_name, source.get_mmproj_file().file_name)
            command = ["./llama-llava-cli", "-m", path_model_file, "--mmproj", path_mmproj_file, "--image", image_path, "-p", prompt ]
            # saving and extracting the result
            log_file = os.path.join(self.path_logs, datautils.gen_timestamp_log_name("llava-result", ".txt"))
            with open(log_file, 'w') as file:
                result = subprocess.run(command, cwd=self.path_install, stdout=file, stderr=subprocess.PIPE)
            if result.returncode != 0:
                raise Exception("Error running LLava: " + result.stderr.decode())
            with open(log_file, 'r') as file:
                return Operation(status=True, payload=file.read())
        except Exception as e:
            return Operation(status=False, error=str(e))



