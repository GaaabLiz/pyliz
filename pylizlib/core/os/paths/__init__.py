"""Path spelling, locations, identity, containment, and safety."""

from pylizlib.core.os.paths.containment import assert_destination_outside_source
from pylizlib.core.os.paths.identity import same_filesystem_entry
from pylizlib.core.os.paths.lexical import (
    get_filename,
    get_filename_no_ext,
    get_second_to_last_directory,
    is_absolute_path,
    normalize_mapped_drive,
    normalize_rooted_path,
)
from pylizlib.core.os.paths.locations import get_app_home_dir, get_home_dir
from pylizlib.core.os.paths.safety import is_critical_system_path

__all__ = [
    "assert_destination_outside_source",
    "get_app_home_dir",
    "get_filename",
    "get_filename_no_ext",
    "get_home_dir",
    "get_second_to_last_directory",
    "is_absolute_path",
    "is_critical_system_path",
    "normalize_mapped_drive",
    "normalize_rooted_path",
    "same_filesystem_entry",
]
