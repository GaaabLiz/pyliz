"""Load snapshot metadata from a storage directory."""

from pathlib import Path

from pylizlib.core.os.snap.domain import Snapshot, validate_directory_component


def get_snapshot_from_path(path_snapshot: Path, json_filename: str) -> Snapshot | None:
    """
    Loads a Snapshot object from a directory containing a snapshot JSON file.

    Args:
        path_snapshot: The path to the snapshot's directory.
        json_filename: The name of the JSON file that contains the snapshot's data.

    Returns:
        A Snapshot object if the file is found and parsed correctly, otherwise None.

    Raises:
        ValueError: If the provided path is a file, not a directory.
        FileNotFoundError: If the path or the JSON file does not exist.
    """
    from pylizlib.core.os.snap.serializer import SnapshotSerializer

    if path_snapshot.is_file():
        raise ValueError(f"The provided path {path_snapshot} is not a directory.")
    if not path_snapshot.exists():
        raise FileNotFoundError(f"The provided path {path_snapshot} does not exist.")
    validate_directory_component(json_filename, "Snapshot JSON filename")
    path_snapshot_json = path_snapshot.joinpath(json_filename)
    if not path_snapshot_json.is_file():
        raise FileNotFoundError(f"No snapshot.json file found in {path_snapshot}.")
    return SnapshotSerializer.from_json(path_snapshot_json)
