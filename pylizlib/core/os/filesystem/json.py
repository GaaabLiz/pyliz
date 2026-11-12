"""JSON serialization to filesystem paths."""

import json
import os
import tempfile


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
    if not os.path.exists(path):
        os.makedirs(path)

    # Serialize first so invalid values cannot truncate an existing file.
    serialized = json.dumps(content, indent=4)
    file_path = os.path.join(path, filename)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path,
            prefix=".json-",
            delete=False,
        ) as json_file:
            temporary_path = json_file.name
            json_file.write(serialized)
            json_file.flush()
            os.fsync(json_file.fileno())
        os.replace(temporary_path, file_path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            try:
                os.unlink(temporary_path)
            except FileNotFoundError:
                pass
