"""Discover executable commands and installed programs."""

import os
import shutil
from pathlib import Path


def is_command_available_with_run(command: str) -> bool:
    """
    Check if a command is available without executing it.
    :param command: The command to check
    :return: True if the command is available, False otherwise
    """
    return shutil.which(command) is not None


def is_command_available(command: str) -> bool:
    return shutil.which(command) is not None


def is_software_installed(exe_path: Path) -> bool:
    """
    Check if a software is installed by checking if the executable file exists
    :param exe_path: The path of the executable file
    :return: True if the software is installed, False otherwise
    """
    return os.path.isfile(exe_path.__str__()) and os.access(exe_path.__str__(), os.X_OK)
