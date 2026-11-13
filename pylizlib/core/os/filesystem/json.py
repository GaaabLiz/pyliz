"""JSON serialization to filesystem paths."""

import json
import os
from pathlib import Path

from pylizlib.core.os.filesystem.atomic import _write_text_atomically


def write_json_to_file(path, filename, content):
    """Serialize JSON and atomically replace a file in its parent directory.

    Args:
        path (str | Path): Parent directory for the output file; created if missing.
        filename (str): Output file name relative to ``path``.
        content (object): JSON-serializable value to write.

    Returns:
        None: The serialized file has replaced the destination.

    Raises:
        TypeError: The value cannot be serialized as JSON.
        OSError: Staging or replacing the output file fails.
    """
    directory = Path(path)
    if not os.path.exists(path):
        os.makedirs(path)

    # Serialize first so invalid values cannot truncate an existing file.
    serialized = json.dumps(content, indent=4)
    _write_text_atomically(directory / filename, serialized, temporary_prefix=".json-")
