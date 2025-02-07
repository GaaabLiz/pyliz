import os
import subprocess
from abc import ABC
from typing import Callable

from git import Repo

from pylizlib.data import datautils
from pylizlib.model.pyliz_script import PylizBaseAction
from pylizlib.os import pathutils, osutils
from pylizlib.os.pathutils import check_path


class ActionGitClone(PylizBaseAction, ABC):

    def __init__(
            self,
            repo: str,
            install_dir: str,
            ignore_if_exists: bool = True,
            logs_dir: str | None = None,
            on_log: Callable[[str], None] = lambda x: None
    ):
        super().__init__()
        self.repo = repo
        self.install_dir = install_dir
        self.ignore_if_exists = ignore_if_exists
        self.logs_dir = logs_dir
        self.on_log = on_log

    def run(self):
        self.on_log("Cloning " + self.repo + "...")
        if os.path.exists(self.install_dir):
            self.on_log("Repo already installed.")
            return
        else:
            self.on_log("Repo not installed. Proceeding...")
            pathutils.check_path(self.install_dir, True)
        Repo.clone_from(self.repo, self.install_dir)
        self.on_log("Done.")

    def reset(self):
        pass


class ActionCommandAvailable(PylizBaseAction, ABC):

    def __init__(self, command: str):
        super().__init__()
        self.command = command

    def run(self):
        status = osutils.is_command_available(self.command)
        if not status:
            raise Exception(self.command + " command not available.")

    def reset(self):
        pass


class ActionTest(PylizBaseAction, ABC):


    def __init__(self, param1: str):
        super().__init__()
        self.param1 = param1


    def run(self):
        print("test " + self.param1)

    def reset(self):
        pass


class ActionExecCli(PylizBaseAction, ABC):

    def __init__(self,
                 path: str,
                 commands: list[str],
                 path_logs: str | None = None,
                 on_log: Callable[[str], None] = lambda x: None,

    ):
        super().__init__()
        self.commands = commands
        self.on_log = on_log
        self.path_install = path
        self.path_logs = path_logs

    def run(self):
        if not os.path.isdir(self.path_install):
            raise ValueError(f"Invalid path_install: {self.path_install}")
        self.on_log("Executing: " + self.commands[0])
        output = subprocess.run(self.commands, check=True, cwd=self.path_install, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.on_log("Done.")
        self.__save_output(output, self.commands[0])

    def __save_output(self, output, name: str):
        if self.path_logs is None:
            return
        check_path(self.path_logs, True)
        log_build_name = datautils.gen_timestamp_log_name(f"{name}-", ".txt")
        log_build_path = os.path.join(self.path_logs, log_build_name)
        with open(log_build_path, "w") as f:
            f.write(output.stdout)
            f.write("***********************************\n")
            f.write(output.stderr)

    def reset(self):
        pass
