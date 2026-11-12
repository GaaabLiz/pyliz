"""Operating-system queries and user-facing system integrations."""

import getpass
import os
import platform
import subprocess
import sys


def open_system_folder(path):
    """
    Open a system folder (or file) in the default file explorer/application.
    :param path: path to the folder or file
    :return:
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Path {path} does not exist!")

    if sys.platform == "win32":
        if hasattr(os, "startfile"):
            os.startfile(path)
        else:
            subprocess.Popen(["explorer", path])
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def is_os_unix() -> bool:
    """
    Check if the operating system is Unix-based (Linux, MacOS)
    :return: True if the operating system is Unix-based, False otherwise
    """
    current_os = platform.system()
    return current_os in ["Linux", "Darwin"]


def is_os_windows() -> bool:
    """
    Check if the operating system is Windows
    :return: True if the operating system is Windows, False otherwise
    """
    current_os = platform.system()
    return current_os == "Windows"


def get_system_username() -> str:
    """
    Get the current system username
    :return: The current system username
    """
    return getpass.getuser()
