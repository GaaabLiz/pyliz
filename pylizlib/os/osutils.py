import os
import shutil
import subprocess
import platform


def get_folder_size_mb(path) -> float:
    """
    Get the size of a folder in megabytes
    :param path: path to the folder
    :return: size of the folder in megabytes
    """
    # Inizializza la dimensione totale a 0
    total_size = 0
    # Scansione delle cartelle e dei file all'interno del percorso dato
    for root, dirs, files in os.walk(path):
        # Aggiungi le dimensioni dei file alla dimensione totale
        for file in files:
            file_path = os.path.join(root, file)
            total_size += os.path.getsize(file_path)
    # Converti la dimensione totale in megabyte (MB)
    total_size_mb = total_size / (1024 * 1024)
    return total_size_mb


def open_system_folder(path):
    """
    Open a system folder in the default file explorer
    :param path: path to the folder
    :return:
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Path {path} does not exist!")
    if os.name == 'nt':  # For Windows
        subprocess.Popen(['explorer', path])
    elif os.name == 'posix':  # For Linux, Mac
        subprocess.Popen(['open', path])
    else:
        raise OSError("Unsupported OS")


def has_disk_free_space(path_of_disk, mb_free):
    """
    Check if a disk has enough free space in megabytes
    :param path_of_disk: The path of the disk to check
    :param mb_free: The minimum amount of free space in megabytes
    :return: True if the disk has enough free space, False otherwise
    """
    stat = shutil.disk_usage(path_of_disk)
    spazio_disponibile_mb = stat.free / (1024 * 1024)
    if spazio_disponibile_mb > mb_free:
        return True
    else:
        return False


def get_free_space_mb(directory) -> float:
    """
    Get the free space in megabytes of a directory
    :param directory: path to the directory
    :return: free space in megabytes
    """
    statvfs = os.statvfs(directory)
    # Calculate the free space in bytes and convert to megabytes
    free_space = statvfs.f_frsize * statvfs.f_bavail / (1024 * 1024)
    return free_space


def get_directory_size(path) -> float:
    """
    Get the size of a directory in megabytes
    :param path: path to the directory
    :return: size of the directory in megabytes
    """
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            total_size += os.path.getsize(fp)
    return total_size / (1024 * 1024)


def check_move_dirs_free_space(src_path, dst_path) -> bool:
    """
    Check if there is enough free space in the destination directory to move the source directory
    :param src_path: The path of the source directory
    :param dst_path: The path of the destination directory
    :return: True if there is enough free space, False otherwise
    """
    # Calculate the size of the source directory
    src_size_mb = get_directory_size(src_path)
    # Get the free space of the destination directory
    free_space_mb = get_free_space_mb(dst_path)
    # Check if there is enough space
    return free_space_mb >= src_size_mb


def is_command_available_with_run(command: str) -> bool:
    """
    Check if a command is available in the system
    :param command: The command to check
    :return: True if the command is available, False otherwise
    """
    try:
        subprocess.run([command], check=True)
        return True
    except FileNotFoundError:
        return False


def is_command_available(command: str) -> bool:
    return shutil.which(command) is not None


def is_os_unix() -> bool:
    """
    Check if the operating system is Unix-based (Linux, MacOS)
    :return: True if the operating system is Unix-based, False otherwise
    """
    current_os = platform.system()
    return current_os in ["Linux", "Darwin"]
