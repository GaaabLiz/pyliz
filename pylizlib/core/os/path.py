import os
import random
import shutil
import tempfile
from pathlib import Path
from typing import Callable, List, Optional, LiteralString

from pylizlib.core.data import gen
from pylizlib.core.log.pylizLogger import logger
from pylizlib.core.os.file import is_video_file, is_image_file


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


def get_filename(path):
    """
    Get the filename from a path
    :param path: path to get the filename from
    :return: the filename from the path
    """
    return os.path.basename(path)


def get_filename_no_ext(path):
    """
    Get the filename without the extension from a path
    :param path: path to get the filename without the extension from
    :return: the filename without the extension from the path
    """
    return os.path.splitext(os.path.basename(path))[0]


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


def dir_contains_image(path: str):
    """
    Check if a directory contains an image file
    :param path: path to the directory to check
    :return: True if the directory contains an image file, False otherwise
    """
    files = scan_directory_match_bool(path, is_image_file)
    return len(files) > 0


def dir_contains_video(path: str):
    """
    Check if a directory contains a video file
    :param path: path to the directory to check
    :return: True if the directory contains a video file, False otherwise
    """
    files = scan_directory_match_bool(path, is_video_file)
    return len(files) > 0


def dir_contains(directory: str, names: list[str], at_least_one: bool = False) -> bool:
    """
    Check if a directory contains a list of folders/files.
    :param directory: path to the directory to check
    :param names: list of folder/files names to check
    :param at_least_one: boolean flag to check if at least one of the folders is present
    :return: True if the directory contains all (or at least one of) the folders/files, False otherwise
    """
    check_path_dir(directory)
    found = 0
    for folder_name in names:
        current = os.path.join(directory, folder_name)
        if os.path.exists(current):
            found += 1
    if at_least_one:
        return found > 0
    return found == len(names)


def get_folders_from(
        directory,
        recursive: bool = False
) -> list[ LiteralString | str | bytes]:
    """
    Get a list of folders paths from a path
    :param directory: path to get the folders from
    :param recursive: boolean flag to scan the directory recursively
    :return: list of folders paths from the path
    """
    if recursive:
        return [os.path.join(root, d) for root, dirs, files in os.walk(directory) for d in dirs]
    return [d for d in os.listdir(directory) if os.path.isdir(os.path.join(directory, d))]


def get_files_from(
        directory,
        recursive:bool = False,
        extension: Optional[str] = None
) -> list[ LiteralString | str | bytes]:
    """
    Get a list of file paths from a path
    :param directory: path to get the files from
    :param recursive: boolean flag to scan the directory recursively
    :param extension: optional extension to filter the files
    :return: list of file paths from the path
    """
    db = []
    if recursive:
        for root, dirs, files in os.walk(directory):
            for file in files:
                db.append(os.path.join(root, file))
    else:
        db = [f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))]
    if extension is not None:
        return [f for f in db if f.endswith(extension)]
    return db


def get_path_items(path: Path, recursive: bool = False) -> list[Path]:
    """
    Get a list of Path items from a Path.
    :param path: Path to get the items from.
    :param recursive: Whether to list items recursively.
    :return: List of Path items from the path.
    """
    items = []

    with os.scandir(path) as entries:
        for entry in entries:
            try:
                entry_path = Path(entry.path)
                items.append(entry_path)

                if recursive and entry.is_dir():
                    items.extend(get_path_items(entry_path, recursive=True))
            except PermissionError:
                continue

    return items


def clear_or_move_to_temp(path: Path, temp_path: Path | None = None, move_to_temp: bool = False):
    """
    Clear a directory or move it to a temporary location.
    :param path: Path to the directory to clear or move.
    :param temp_path: Path to the temporary directory.
    :param move_to_temp: Whether to move the directory to a temporary location instead of deleting it.
    :return: None
    """
    if not move_to_temp:
        shutil.rmtree(path.__str__())
    else:
        if temp_path is None:
            logger.error("Temp path cannot be None")
            return
        temp_dir = tempfile.gettempdir()
        atom_temp_dir = os.path.join(temp_dir, temp_path.__str__())
        os.makedirs(atom_temp_dir, exist_ok=True)
        dest_name = os.path.basename(path.__str__() + "_" + gen.gen_random_string(10))
        dest_path = os.path.join(atom_temp_dir, dest_name)
        shutil.move(path, dest_path)


def random_subfolder(path: Path) -> Path:
    subdirs = [p for p in path.iterdir() if p.is_dir()]
    if not subdirs:
        return None  # o lancia un'eccezione, a seconda delle esigenze
    return random.choice(subdirs)


def clear_folder_contents(path: Path):
    """
    Clear all contents of a folder without deleting the folder itself.
    :param path: Path to the folder to clear.
    :return: None
    """
    if not path.is_dir():
        raise NotADirectoryError(f"The provided path {path} is not a directory.")
    for item in path.iterdir():
        try:
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
        except Exception as e:
            logger.error(f"Error deleting {item}: {e}")


def count_items(dir_path: Path) -> int:
    """
    Restituisce il numero di file e sottodirectory in dir_path.
    """
    if not dir_path.is_dir():
        raise ValueError(f"{dir_path!r} non è una directory valida")
    return sum(1 for _ in dir_path.iterdir())


def duplicate_directory(
        src_dir: Path,
        dest_dir: Path | None = None,
        copy_suffix: str = "_copy"
) -> Path:
    """
    Duplica la directory src_dir in dest_dir e ritorna il Path della copia.

    Se dest_dir è None, crea una directory fratello di src_dir
    con nome src_dir.name + copy_suffix.
    """
    if not src_dir.is_dir():
        raise ValueError(f"{src_dir!r} non è una directory valida")

    # Se non specificato, costruisce dest_dir affiancata a src_dir
    if dest_dir is None:
        dest_dir = src_dir.with_name(src_dir.name + copy_suffix)

    # Assicura che la destinazione non esista già
    if dest_dir.exists():
        raise FileExistsError(f"{dest_dir!r} esiste già")

    # Copia ricorsivamente la directory
    shutil.copytree(src_dir, dest_dir)
    return dest_dir


# def path_match_items(path: Path, path_list: list[str]):
#     """
#     Check the number and percentage of items in a path that match a list of strings paths.
#     :param path: Path to check.
#     :param path_list: List of strings paths to match.
#     :return: Tuple containing the number of items matched and percentage of items matched.
#     """
#     items_path = get_path_items(path, recursive=True)
#     items_path_relative = [str(p.relative_to(path)) for p in items_path]
#
#     set1, set2 = set(items_path_relative), set(path_list)
#     intersection = len(set1 & set2)
#     union = len(set1 | set2)
#     perc = (intersection / union) * 100 if union > 0 else 100
#
#     return intersection, perc


class PathMatcher:

    def __init__(self):
        self.working_path_items_rel = None
        self.working_path_items = None
        self.working_path = None

    def load_path(self, path: Path, recursive: bool = False):
        self.working_path = path
        self.working_path_items = get_path_items(path, recursive)
        self.working_path_items_rel = [str(p.relative_to(self.working_path)) for p in self.working_path_items]

    def match_with_list(self, path_str_list: list[str]):
        set1, set2 = set(self.working_path_items_rel), set(path_str_list)
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        perc = (intersection / union) * 100 if union > 0 else 100
        return intersection, perc

    def match_with_file_list(self, file_path: Path):
        with open(file_path, "r") as file:
            return self.match_with_list([line.strip() for line in file.readlines()])

    def export_file_list(self, save_file_path: Path, name: str = "output.txt"):
        with open(save_file_path.joinpath(name), "w+") as file:
            for item in self.working_path_items_rel:
                file.write(f"{item}\n")

    def log_all(self):
        logger.trace(f"Working path: {self.working_path}")
        for item in self.working_path_items_rel:
            print(item)



