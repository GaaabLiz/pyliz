import os
import subprocess
from typing import Callable

from git import Repo

from ai.model.ai_method import AiMethod
from ai.model.ai_models import AiModels
from ai.model.ai_power import AiPower
from util import pathutils, osutils, fileutils


class LlamaCpp:

    GITHUB_URL = "https://github.com/ggerganov/llama.cpp.git"

    def __init__(self, path_install: str, path_models: str):
        self.path_install = path_install
        self.path_models = path_models
        # self.main_dir = os.path.join(self.path_install, "llama.cpp")

    def clone_and_build(self, on_log: Callable[[str], None]):
        # check if the folder already exists
        if os.path.exists(self.path_install):
            on_log("LlamaCpp already installed.")
            return
        # Cloning github repo
        on_log("Cloning LlamaCpp...")
        Repo.clone_from(LlamaCpp.GITHUB_URL, self.path_install)
        on_log("Clone successful.")
        # Building sources with make
        on_log("Building sources...")
        if not osutils.is_command_available("make"):
            raise Exception("Make command not available. Plaase install make.")
        pathutils.check_path_dir(self.path_install)
        risultato = subprocess.run(["make"], check=True, cwd=self.path_install, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        on_log("Build successful.")

    def install_llava(
            self,
            power: AiPower,
            on_log: Callable[[str], None],
            on_progress: Callable[[int], None]
    ):
        self.clone_and_build(on_log)
        on_log("Installing LLava...")
        source = AiModels.get_llava(power, AiMethod.LLAVA_LOCAL_LLAMACPP)
        folder = os.path.join(self.path_models, source.local_name)
        pathutils.check_path(folder, True)
        pathutils.check_path_dir(folder)
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