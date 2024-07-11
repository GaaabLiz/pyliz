import logging
import os
from datetime import datetime

# Global logger instances
rootConsoleLogger = logging.getLogger(__name__ + ".console")
rootFileLogger = logging.getLogger(__name__ + ".file")

# Default values for Loggiz
default_console_log_level = logging.DEBUG
default_console_log_format = "[%(levelname)s]: %(message)s"
default_file_log_level = logging.DEBUG
default_file_log_format = "%(asctime)s - [%(levelname)s]: %(message)s"
default_tag_char_start = "("
default_tag_char_end = "): "


class Loggiz:
    @staticmethod
    def setup(
            app_name="app",
            setup_console=True,
            setup_file=True,
            console_level=default_console_log_level,
            console_format=default_console_log_format,
            console_ansi=False,
            file_level=default_file_log_level,
            file_format=default_file_log_format,
            file_log_base_path="",
            file_log_folder_name="logs",
            file_log_name="latest.log",
            use_app_timestamp_template=True,
    ):
        if setup_file:
            if use_app_timestamp_template:
                file_log_name = Loggiz.create_timestamp_log_file_name(app_name)
            else:
                file_log_name = file_log_name
            log_folder_dir = os.path.join(file_log_base_path, file_log_folder_name)
            file_full_path = os.path.join(log_folder_dir, file_log_name)
            if not os.path.exists(log_folder_dir):
                os.makedirs(log_folder_dir)
            config.set_file_log_path(file_full_path)
            config.set_logger_file_enabled(True)
            Loggiz.setup_file(
                level=file_level,
                log_format=file_format,
                file_path=file_full_path,
            )

        if setup_console:
            Loggiz.setup_console(
                level=console_level,
                log_format=console_format,
            )
            config.set_console_ansi(console_ansi)
            config.set_logger_console_enabled(True)


    @staticmethod
    def setup_console(level=default_console_log_level, log_format=default_console_log_format):
        rootConsoleLogger.setLevel(level)
        console_handler = logging.StreamHandler()
        console_formatter = logging.Formatter(log_format)
        console_handler.setFormatter(console_formatter)
        rootConsoleLogger.addHandler(console_handler)

    @staticmethod
    def setup_file(level=default_file_log_level, log_format=default_file_log_format, file_path="loggiz.log"):
        rootFileLogger.setLevel(level)
        file_handler = logging.FileHandler(file_path)
        file_formatter = logging.Formatter(log_format)
        file_handler.setFormatter(file_formatter)
        rootFileLogger.addHandler(file_handler)

    @staticmethod
    def create_timestamp_log_file_name(app_name):
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_file_name = f"{app_name}_{timestamp}.log"
        return log_file_name

    @staticmethod
    def create_timestamp_log_file_path(app_name, log_dir):
        log_file_name = Loggiz.create_timestamp_log_file_name(app_name)
        log_file_path = os.path.join(log_dir, log_file_name)
        return log_file_path


# Config class for Loggiz
class LoggizConfig:
    def __init__(self):
        self.enable_file_ansi = False
        self.enable_console_ansi = False
        self.tag_char_start = default_tag_char_start
        self.tag_char_end = default_tag_char_end
        self.file_log_path = ""
        self.logger_console_enabled = False
        self.logger_file_enabled = False

    def set_console_ansi(self, ansi):
        self.enable_console_ansi = ansi

    def set_file_ansi(self, ansi):
        self.enable_file_ansi = ansi

    def set_tag_chars(self, start, end):
        self.tag_char_start = start
        self.tag_char_end = end

    def set_file_log_path(self, path):
        self.file_log_path = path

    def set_logger_console_enabled(self, enabled):
        self.logger_console_enabled = enabled

    def set_logger_file_enabled(self, enabled):
        self.logger_file_enabled = enabled


# ANSI color codes
class Colors:
    BLACK = "\033[0;30m"
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    BROWN = "\033[0;33m"
    BLUE = "\033[0;34m"
    PURPLE = "\033[0;35m"
    CYAN = "\033[0;36m"
    LIGHT_GRAY = "\033[0;37m"
    DARK_GRAY = "\033[1;30m"
    LIGHT_RED = "\033[1;31m"
    LIGHT_GREEN = "\033[1;32m"
    YELLOW = "\033[1;33m"
    LIGHT_BLUE = "\033[1;34m"
    LIGHT_PURPLE = "\033[1;35m"
    LIGHT_CYAN = "\033[1;36m"
    LIGHT_WHITE = "\033[1;37m"
    BOLD = "\033[1m"
    FAINT = "\033[2m"
    ITALIC = "\033[3m"
    UNDERLINE = "\033[4m"
    BLINK = "\033[5m"
    NEGATIVE = "\033[7m"
    CROSSED = "\033[9m"
    END = "\033[0m"
    if not __import__("sys").stdout.isatty():
        for _ in dir():
            if isinstance(_, str) and _[0] != "_":
                locals()[_] = ""
    else:
        if __import__("platform").system() == "Windows":
            kernel32 = __import__("ctypes").windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
            del kernel32


config = LoggizConfig()  # Current configuration for Loggiz


class LoggizLogger:

    @staticmethod
    def get_tag_string(tag, ansify=False):
        if ansify:
            return f"{Colors.LIGHT_WHITE}{config.tag_char_start}{tag}{config.tag_char_end}{Colors.END}"
        else:
            return f"{config.tag_char_start}{tag}{config.tag_char_end}"

    @staticmethod
    def print_separator(sep, count):
        string = f'{sep}' * count
        if config.enable_console_ansi:
            print(Colors.LIGHT_GRAY + string + Colors.END)
        else:
            print(string)

    # ------------------------ CONSOLE LOGGING ------------------------

    @staticmethod
    def log_console_debug(tag, message):
        if config.enable_console_ansi:
            rootConsoleLogger.debug(LoggizLogger.get_tag_string(tag, True) + Colors.CYAN + f"{message}" + Colors.END)
        else:
            rootConsoleLogger.debug(LoggizLogger.get_tag_string(tag) + message)

    @staticmethod
    def log_console_info(tag, message):
        if config.enable_console_ansi:
            rootConsoleLogger.info(LoggizLogger.get_tag_string(tag, True) + Colors.GREEN + f"{message}" + Colors.END)
        else:
            rootConsoleLogger.info(LoggizLogger.get_tag_string(tag) + message)

    @staticmethod
    def log_console_warning(tag, message):
        if config.enable_console_ansi:
            rootConsoleLogger.warning(LoggizLogger.get_tag_string(tag, True) + Colors.YELLOW + f"{message}" + Colors.END)
        else:
            rootConsoleLogger.warning(LoggizLogger.get_tag_string(tag) + message)

    @staticmethod
    def log_console_error(tag, message):
        if config.enable_console_ansi:
            rootConsoleLogger.error(LoggizLogger.get_tag_string(tag, True) + Colors.RED + f"{message}" + Colors.END)
        else:
            rootConsoleLogger.error(LoggizLogger.get_tag_string(tag) + message)

    # ------------------------ FILE LOGGING ------------------------

    @staticmethod
    def log_file_debug(tag, message):
        rootFileLogger.debug(LoggizLogger.get_tag_string(tag) + message)

    @staticmethod
    def log_file_info(tag, message):
        rootFileLogger.info(LoggizLogger.get_tag_string(tag) + message)

    @staticmethod
    def log_file_warning(tag, message):
        rootFileLogger.warning(LoggizLogger.get_tag_string(tag) + message)

    @staticmethod
    def log_file_error(tag, message):
        rootFileLogger.error(LoggizLogger.get_tag_string(tag) + message)

    # ------------------------  LOGGING METHODS ------------------------

    @staticmethod
    def debug_tag(tag, message):
        if config.logger_console_enabled:
            LoggizLogger.log_console_debug(tag, message)
        if config.logger_file_enabled:
            LoggizLogger.log_file_debug(tag, message)

    @staticmethod
    def info_tag(tag, message):
        if config.logger_console_enabled:
            LoggizLogger.log_console_info(tag, message)
        if config.logger_file_enabled:
            LoggizLogger.log_file_info(tag, message)

    @staticmethod
    def warning_tag(tag, message):
        if config.logger_console_enabled:
            LoggizLogger.log_console_warning(tag, message)
        if config.logger_file_enabled:
            LoggizLogger.log_file_warning(tag, message)

    @staticmethod
    def error_tag(tag, message):
        if config.logger_console_enabled:
            LoggizLogger.log_console_error(tag, message)
        if config.logger_file_enabled:
            LoggizLogger.log_file_error(tag, message)




