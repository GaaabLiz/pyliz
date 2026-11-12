"""Compatibility checks for historical OS helper modules."""

import pylizlib.core.os.file as legacy_file
import pylizlib.core.os.path as legacy_path
import pylizlib.core.os.utils as legacy_utils
from pylizlib.core.network import download
from pylizlib.core.os import commands, system
from pylizlib.core.os.filesystem import capacity, directories, file_types, files, json
from pylizlib.core.os.paths import lexical, locations, safety
from pylizlib.core.os.windows import processes


def test_path_facade_reexports_helpers_from_focused_modules():
    assert legacy_path.get_filename is lexical.get_filename
    assert legacy_path.get_app_home_dir is locations.get_app_home_dir
    assert legacy_path.PathMatcher is directories.PathMatcher


def test_utils_facade_reexports_helpers_from_focused_modules():
    assert legacy_utils.is_critical_system_path is safety.is_critical_system_path
    assert legacy_utils.get_directory_size is capacity.get_directory_size
    assert legacy_utils.is_command_available is commands.is_command_available
    assert legacy_utils.open_system_folder is system.open_system_folder
    assert legacy_utils.WindowsOsUtils is processes.WindowsOsUtils


def test_file_facade_reexports_helpers_from_focused_modules():
    assert legacy_file.get_file_type is file_types.get_file_type
    assert legacy_file.get_file_c_date is files.get_file_c_date
    assert legacy_file.download_file is download.download_file
    assert legacy_file.write_json_to_file is json.write_json_to_file
