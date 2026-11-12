"""Compatibility exports for legacy path and directory helpers.

Path spelling helpers live in ``paths``; directory operations live in
``filesystem.directories``. This module preserves historical imports.
"""

from pylizlib.core.os.filesystem.directories import (
    PathMatcher,
    check_path,
    check_path_dir,
    check_path_file,
    clear_folder_contents,
    count_items,
    count_pathsub_dirs,
    count_pathsub_elements,
    count_pathsub_files,
    create_path,
    dir_contains,
    dir_contains_image,
    dir_contains_video,
    duplicate_directory,
    get_files_from,
    get_folders_from,
    get_path_items,
    random_subfolder,
    remove_directory_or_move_to_temp,
    scan_directory,
    scan_directory_match_bool,
)
from pylizlib.core.os.paths.lexical import get_filename, get_filename_no_ext, get_second_to_last_directory
from pylizlib.core.os.paths.locations import get_app_home_dir, get_home_dir

__all__ = [
    "PathMatcher",
    "check_path",
    "check_path_dir",
    "check_path_file",
    "clear_folder_contents",
    "count_items",
    "count_pathsub_dirs",
    "count_pathsub_elements",
    "count_pathsub_files",
    "create_path",
    "dir_contains",
    "dir_contains_image",
    "dir_contains_video",
    "duplicate_directory",
    "get_app_home_dir",
    "get_filename",
    "get_filename_no_ext",
    "get_files_from",
    "get_folders_from",
    "get_home_dir",
    "get_path_items",
    "get_second_to_last_directory",
    "random_subfolder",
    "remove_directory_or_move_to_temp",
    "scan_directory",
    "scan_directory_match_bool",
]
