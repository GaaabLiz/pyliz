"""Compatibility imports for filesystem tree operations used by snapshots."""

from pylizlib.core.os.filesystem.tree import (
    assert_destination_outside_source as assert_destination_outside_source,
)
from pylizlib.core.os.filesystem.tree import (
    assert_no_symlinks as assert_no_symlinks,
)
from pylizlib.core.os.filesystem.tree import (
    is_link_or_junction as is_link_or_junction,
)
from pylizlib.core.os.filesystem.tree import (
    iter_files_strict as iter_files_strict,
)
from pylizlib.core.os.filesystem.tree import (
    iter_tree_entries_strict as iter_tree_entries_strict,
)
