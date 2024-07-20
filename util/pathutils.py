import os
from typing import Callable, List


def get_home_dir():
    """
    Get the home directory of the current user
    :return: The home directory of the current user
    """
    return os.path.expanduser("~")


def get_app_home_dir(app_name, create_if_not: bool = True):
    """
    create and return the home directory for the application
    :param create_if_not: boolean flag to create the directory if it does not exist
    :param app_name:  name of the application
    :return: home directory for the application
    """
    home_dir = get_home_dir()
    app_home_dir = os.path.join(home_dir, app_name)
    if create_if_not:
        if not os.path.exists(app_home_dir):
            os.makedirs(app_home_dir)
    return app_home_dir


def create_path(path):
    """
    Create a path if it does not exist
    :param path: path to create
    :return:
    """
    if not os.path.exists(path):
        os.makedirs(path)


def check_path(path, create_if_not: bool = False) -> bool:
    """
    Check if the path exists and is readable
    :param path: path to check
    :param create_if_not: create the path if it does not exist
    :return: True if the path exists and is readable, False otherwise
    """
    if not os.path.exists(path):
        if create_if_not:
            os.makedirs(path)
            return False
        else:
            return False
    if not os.access(path, os.R_OK):
        return False
    return True


def check_path_dir(path):
    """
    Check if the path:
    - exists and is readable and writable
    - is a directory
    If any of the conditions is not met, an exception is raised
    :param path:  path to check
    :return:
    """
    # Check if the path exists and is readable
    if not os.path.exists(path):
        raise IOError(f'Path {path} does not exist!')
    if not os.access(path, os.R_OK):
        raise PermissionError(f'Path {path} is not readable!')
    if not os.access(path, os.W_OK):
        raise PermissionError(f'Path {path} is not writable!')
    # Check if the path is a directory
    if not os.path.isdir(path):
        raise NotADirectoryError(f'Path {path} is not a directory!')
    if not os.access(path, os.W_OK):
        raise PermissionError(f'Path {path} is not writable!')


def check_path_file(path: str):
    """
    Check if the path:
    - exists and is readable and writable
    - is a file
    If any of the conditions is not met, an exception is raised
    :param path:  path to check
    :return:
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"File {path} does not exist!")
    if not os.access(path, os.R_OK):
        raise PermissionError(f"File {path} is not readable!")
    if not os.access(path, os.W_OK):
        raise PermissionError(f"File {path} is not writable!")
    if not os.path.isfile(path):
        raise NotADirectoryError(f"Path {path} is not a file!")


def get_second_to_last_directory(path):
    """
    Get the second to last directory in a path as a string
    :param path: path string to get the second to last directory from
    :return: the second to last directory in the path as a string (only name not path).
    """
    # Divide il percorso in una lista di componenti
    path_components = os.path.normpath(path).split(os.sep)
    # Controlla che il percorso abbia almeno due componenti
    if len(path_components) < 2:
        return None
    # Restituisce il secondo componente dal fondo della lista
    return path_components[-2]


def count_pathsub_files(path):
    """
    Count the number of files in a path including subdirectories
    :param path: path to count files from
    :return: the number of files in the path including subdirectories
    """
    count = 0
    for root, dirs, files in os.walk(path):
        count += len(files)
    return count


def count_pathsub_dirs(path):
    """
    Count the number of directories in a path including subdirectories
    :param path: path to count directories from
    :return: the number of directories in the path including subdirectories
    """
    count = 0
    for root, dirs, files in os.walk(path):
        count += len(dirs)
    return count


def count_pathsub_elements(path):
    """
    Count the number of files and directories in a path including subdirectories
    :param path: path to count files and directories from
    :return: the number of files and directories in the path including subdirectories
    """
    count = 0
    for root, dirs, files in os.walk(path):
        count += len(files) + len(dirs)
    return count


def scan_directory(path: str, on_file, on_folder):
    """
    Scan a directory and call the on_file and on_folder functions for each file and folder found
    :param path: The path to scan
    :param on_file: function to call for each file found
    :param on_folder: function to call for each folder found
    :return:
    """
    for root, dirs, files in os.walk(path):
        for file in files:
            on_file(file)
        for dir in dirs:
            scan_directory(os.path.join(root, dir), on_file, on_folder)


def scan_directory_match_bool(path: str, to_be_add: Callable[[str], bool]) -> List[str]:
    """
    Scan a directory and return a list of files that match the to_be_add function
    :param path: The path to scan
    :param to_be_add: function to call for each file found to check if it should be added to the final list.
    :return: list of files that match the to_be_add function
    """
    matching_files = []
    for root, dirs, files in os.walk(path):
        for file in files:
            file_path = os.path.join(root, file)
            if to_be_add(file_path):
                matching_files.append(file_path)
    return matching_files



