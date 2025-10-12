import getpass
import os
import shutil
import subprocess
import platform
from pathlib import Path

import psutil


PATH_DEFAULT_GIT_BASH = Path(r"C:\Program Files\Git\bin\bash.exe")


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

def is_os_windows() -> bool:
    """
    Check if the operating system is Windows
    :return: True if the operating system is Windows, False otherwise
    """
    current_os = platform.system()
    return current_os == "Windows"

def is_software_installed(exe_path: Path) -> bool:
    """
    Check if a software is installed by checking if the executable file exists
    :param exe_path: The path of the executable file
    :return: True if the software is installed, False otherwise
    """
    return os.path.isfile(exe_path.__str__()) and os.access(exe_path.__str__(), os.X_OK)


def get_system_username() -> str:
    """
    Get the current system username
    :return: The current system username
    """
    return getpass.getuser()


class WindowsOsUtils:

    @staticmethod
    def is_exe_running(exe_path: Path) -> bool:
        """
        Check if an executable is running
        :param exe_path: The path of the executable file
        :return: True if the executable is running, False otherwise
        """
        exe_path_str = os.path.abspath(exe_path.__str__())  # normalize
        for proc in psutil.process_iter(['exe', 'name']):
            try:
                if proc.info['exe'] and os.path.abspath(proc.info['exe']) == exe_path_str:
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return False

    @staticmethod
    def get_windows_exe_version(exe_path: Path) -> str:
        """
        Get the version of a Windows executable
        if the version information is not available, returns "N/A"
        if the OS is not Windows, returns N/A
        :param exe_path: the path of the executable file
        :return:  The version of the executable or "N/A" if not available
        """
        if not is_os_windows():
            return "N/A"
        import win32api
        try:
            info = win32api.GetFileVersionInfo(exe_path.__str__(), "\\")
            # Le chiavi di versione sono memorizzate come tuple
            # Prima otteniamo la lingua e il codice di pagina
            lang, codepage = win32api.GetFileVersionInfo(exe_path.__str__(), "\\VarFileInfo\\Translation")[0]
            str_info_path = f"\\StringFileInfo\\{lang:04X}{codepage:04X}\\ProductVersion"
            version = win32api.GetFileVersionInfo(exe_path.__str__(), str_info_path)
            return version
        except Exception:
            return "N/A"

    def get_service_executable_path(service_name: str) -> str | None:
        """
        Get the executable path of a Windows service
        If the os is not Windows, returns None
        :param service_name: The name of the service
        :return: The executable path of the service or None if not found
        """
        if not is_os_windows():
            return None
        import winreg
        try:
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                 rf"SYSTEM\CurrentControlSet\Services\{service_name}")
            image_path, _ = winreg.QueryValueEx(key, "ImagePath")
            winreg.CloseKey(key)
            # Rimuove eventuali argomenti e prende solo il percorso
            image_path = image_path.strip()
            if image_path.startswith('"'):
                # Prende il contenuto tra le virgolette
                image_path = image_path.split('"')[1]
            else:
                # Prende la prima parte fino al primo spazio (se non ci sono virgolette)
                parts = image_path.split(' ')
                # Ricostruisce il percorso se contiene spazi e termina con .exe
                exe_parts = []
                for part in parts:
                    exe_parts.append(part)
                    if part.lower().endswith('.exe'):
                        break
                image_path = ' '.join(exe_parts)
            return image_path
        except Exception:
            return None


    def is_service_running(service_name: str) -> bool:
        """
        Check if a Windows service is running
        :param service_name: The name of the service
        :return: True if the service is running, False otherwise
        """
        import win32service
        import win32serviceutil
        try:
            status = win32serviceutil.QueryServiceStatus(service_name)[1]
            return status == win32service.SERVICE_RUNNING
        except Exception:
            return False

    def get_service_version(service_name: str) -> str | None:
        """
        Get the version of a Windows service by checking the version of its executable
        :param service_name: The name of the service
        :return: The version of the service or None if not found
        """
        import win32api
        path = WindowsOsUtils.get_service_executable_path(service_name)
        if path is None:
            return None
        try:
            # Funzione per ottenere versione dal file binario
            info = win32api.GetFileVersionInfo(path, '\\')
            ms = info['FileVersionMS']
            ls = info['FileVersionLS']
            version = f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"
            return version
        except Exception:
            return "N/A"