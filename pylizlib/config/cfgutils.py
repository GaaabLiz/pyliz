import configparser
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List

import rich

from pylizlib.log.pylizLogger import logger


class CfgItem:
    """
    A class to represent a configuration item.
    """

    def __init__(self, section: str, key: str, value: str | bool):
        """
        Constructor for the CfgItem class.
        :param section: The section of the configuration item.
        :param key: The key of the configuration item.
        :param value: The value of the configuration item.
        """
        self.section = section
        self.key = key
        self.value = value


class Cfgini:
    def __init__(self, path_to_ini):
        self.config = None
        self.path = path_to_ini

    def exists(self):
        return os.path.exists(self.path)

    def create(self, items: List[CfgItem] | None = None):
        self.config = configparser.ConfigParser()
        list_of_sections = set()

        for item in items:
            list_of_sections.add(item.section)

        for section in list_of_sections:
            self.config.add_section(section)

        for item in items:
            self.config.set(item.section, item.key, item.value)

        try:
            with open(self.path, 'w') as configfile:
                self.config.write(configfile)
        except Exception as e:
            logger.error("Error while creating configuration file: ", e)

    def read(self, section, key, is_bool=False):
        self.config = configparser.ConfigParser()
        self.config.read(self.path)
        if not self.config.has_section(section):
            logger.warning(f"Attenzione: La sezione '{section}' non esiste nel file INI.")
            return None
        if not self.config.has_option(section, key):
            logger.warning(f"Attenzione: La chiave '{key}' non esiste nella sezione '{section}'.")
            return None
        try:
            if is_bool:
                return self.config.getboolean(section, key)
            return self.config.get(section, key)
        except configparser.Error as e:
            logger.error(f"Errore durante la lettura di '{key}' in '{section}': {e}")
            return None

    def write(self, section, key, value: str | bool):
        self.config = configparser.ConfigParser()
        self.config.read(self.path)
        if not self.config.has_section(section):
            self.config.add_section(section)
        if isinstance(value, bool):
            self.config.set(section, key, str(value))
        else:
            self.config.set(section, key, value)
        with open(self.path, 'w') as configfile:
            self.config.write(configfile)


@dataclass
class CfgPath:
    path: Path

    def __check_ini(self, path, keys: bool = False, sections: bool = True):
        config = configparser.ConfigParser()
        config.read(path)
        if sections:
            rich.print(f"Sections in {path}:")
            for section in config.sections():
                rich.print(f"  - [magenta]{section}[/magenta]")

    def __find_ini_files(self, directory: str, keys: bool = False, sections: bool = True):
        for root, _, files in os.walk(directory):
            for file in files:
                if file.endswith('.ini'):
                    file_path = os.path.join(root, file)
                    try:
                        self.__check_ini(file_path, keys, sections)
                    except Exception as e:
                        rich.print(f"[red]Error processing {file_path}[/red]: {e}")

    def check_duplicates(self, keys: bool = False, sections: bool = True):
        self.__find_ini_files(str(self.path), keys, sections)


