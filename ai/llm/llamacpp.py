import os
import subprocess
from typing import Callable

from git import Repo

from ai.model.ai_method import AiMethod
from ai.model.ai_models import AiModels
from ai.model.ai_power import AiPower
from util import pathutils, osutils, fileutils, datautils


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

    def clone_and_build(self, on_log: Callable[[str], None]):
        # check if the folder already exists
        if os.path.exists(self.path_install):
            on_log("LlamaCpp already installed.")
            return
        # Cloning github repo
        on_log("Cloning LlamaCpp...")
        Repo.clone_from(LlamaCpp.GITHUB_URL, self.path_install)
        on_log("Clone successful.")
        # Checking if make command is available
        on_log("Building sources...")
        if not osutils.is_command_available("make"):
            raise Exception("Make command not available. Please install make.")
        # checking install folder
        pathutils.check_path_dir(self.path_install)
        # Build the project
        risultato = subprocess.run(["make"], check=True, cwd=self.path_install, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        # create log file
        log_build_folder = os.path.join(self.path_logs, "build")
        log_build_name = datautils.gen_timestamp_log_name("llamacpp-", ".txt")
        log_build_path = os.path.join(log_build_folder, log_build_name)
        pathutils.check_path(log_build_folder, True)
        with open(log_build_path, "w") as f:
            f.write(risultato.stdout)
            f.write("***********************************\n")
            f.write(risultato.stderr)
        on_log("Build successful.")

    def install_llava(
            self,
            power: AiPower,
            on_log: Callable[[str], None],
            on_progress: Callable[[int], None]
    ):
        self.clone_and_build(on_log)
        on_log("Installing LLava...")
        # creating and checking files/folders
        source = AiModels.get_llava(power, AiMethod.LLAVA_LOCAL_LLAMACPP)
        folder = os.path.join(self.path_models, source.local_name)
        pathutils.check_path(folder, True)
        pathutils.check_path_dir(folder)
        # Checking available space
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
        on_log("LLava model installed.")

    def run_llava(
            self,
            power: AiPower,
            image_path: str,
            prompt: str,
    ):
        source = AiModels.get_llava(power, AiMethod.LLAVA_LOCAL_LLAMACPP)
        folder = os.path.join(self.path_models, source.local_name)
        if not os.path.exists(folder):
            raise Exception("LLava model not installed.")
        # Run the model
        command = [
            "./llama-llava-cli",
            "-m",
            os.path.join(self.path_models, source.local_name, source.get_ggml_file().file_name),
            "--mmproj",
            os.path.join(self.path_models, source.local_name, source.get_mmproj_file().file_name),
            "--image",
            image_path,
            "-p",
            prompt
        ]
        log_file = os.path.join(self.path_logs, datautils.gen_timestamp_log_name("llava-result", ".txt"))
        with open(log_file, 'w') as file:
            result = subprocess.run(command, cwd=self.path_install, stdout=file, stderr=subprocess.PIPE)
        if result.returncode != 0:
            raise Exception("Error running LLava: " + result.stderr.decode())
        with open(log_file, 'r') as file:
            return file.read()
