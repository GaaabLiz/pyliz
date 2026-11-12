"""Snapshot JSON conversion and protected metadata file access."""

import json
from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime
from enum import Enum
from pathlib import Path

from pylizlib.core.os.filesystem.atomic import AtomicFile
from pylizlib.core.os.snap.domain import SnapDirAssociation, Snapshot, validate_directory_component
from pylizlib.core.os.snap.storage.original_paths import is_absolute_original_path


class MetadataDurabilityError(OSError):
    """Report metadata already published before its final directory flush failed.

    Attributes:
        path (Path): Destination now containing the new version.
        published (bool): Always True; rollback must not assume publication failed.
        durability_confirmed (bool): Always False because directory sync failed.
    """

    def __init__(self, path: Path, cause: OSError):
        """Store an already-published destination and its failed durability request.

        Args:
            path (Path): Metadata path whose new version is visible.
            cause (OSError): Final directory-flush error included in the message.

        Returns:
            None: The exception stores path and publication flags.
        """
        super().__init__(f"Metadata '{path}' was published atomically, but storage durability could not be confirmed: {cause}")
        self.path = Path(path)
        self.published = True
        self.durability_confirmed = False


class MetadataFile(AtomicFile):
    """Preserve snapshot metadata error messages over general protected file I/O.

    Inherited operations retain prior bytes in a hidden sibling and expose a
    MetadataDurabilityError when publication succeeded but the final flush failed.
    Serializer callers may still supply their protected-open hook explicitly.
    """

    path_label = "Snapshot metadata"
    temporary_label = "Snapshot temporary metadata"
    contents_label = "Metadata"
    durability_error = MetadataDurabilityError


class SnapshotJsonCodec:
    """Convert snapshot metadata in memory without choosing a file I/O policy.

    Decoding retains legacy defaults and invokes the domain constructors. A
    missing captured size remains unknown; loading metadata never scans source
    paths, which may refer to remote storage.
    """

    @staticmethod
    def convert(o):
        """
        Converts non-serializable objects for JSON dumping.

        Args:
            o: The object to convert.

        Returns:
            A serializable representation of the object.

        Raises:
            TypeError: If the object type is not supported.
        """
        if isinstance(o, datetime):
            return o.isoformat()
        if isinstance(o, Enum):
            return o.value  # or o.name if you prefer the name
        raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")

    @staticmethod
    def encode(snapshot: Snapshot, converter: Callable | None = None) -> str:
        """
        Validate and encode a snapshot using the existing indented JSON format.

        The optional converter retains the public serializer customization hook.
        File access is intentionally left to the caller.
        """
        data_dict = SnapshotJsonCodec.snapshot_data(snapshot)
        return SnapshotJsonCodec.encode_data(data_dict, converter)

    @staticmethod
    def decode(contents: str) -> Snapshot:
        """Decode JSON text with legacy date/default handling and domain validation."""
        data = json.loads(contents)
        if not isinstance(data, dict):
            raise ValueError("Snapshot JSON root must be an object.")

        # Convert datetime fields from ISO8601 string to datetime
        for key in [
            "date_created",
            "date_modified",
            "date_last_used",
            "date_last_modified",
            "capture_started_at",
            "capture_completed_at",
        ]:
            if key in data and data[key] is not None:
                data[key] = datetime.fromisoformat(data[key])

        # Convert 'directories' into a list of SnapDirAssociation
        if "directories" in data and isinstance(data["directories"], list):
            if any(not isinstance(directory, dict) for directory in data["directories"]):
                raise ValueError("Snapshot JSON directories must contain objects.")
            associations = []
            for directory_data in data["directories"]:
                association_data = dict(directory_data)
                original_path = association_data.get("original_path")
                if not is_absolute_original_path(original_path):
                    raise ValueError("Snapshot JSON association original_path must be absolute; relative paths cannot be resolved safely.")
                has_storage_name = "storage_name" in association_data
                storage_name = association_data.pop("storage_name", None)
                association = SnapDirAssociation(**association_data)
                association._set_storage_name(storage_name if has_storage_name else association._legacy_directory_name)
                associations.append(association)
            data["directories"] = associations
        elif "directories" in data:
            raise ValueError("Snapshot JSON directories must be a list.")

        if "os_created" not in data:
            import platform

            data["os_created"] = platform.system()

        snapshot = Snapshot(**data)
        snapshot.validate()
        return snapshot

    @staticmethod
    def update_field(contents: str, field_name: str, new_value, converter: Callable | None = None) -> str:
        """Patch a raw JSON object, preserving fields unknown to Snapshot.

        This intentionally does not decode the domain model or add validation.
        The legacy partial-update API accepts arbitrary JSON object fields.
        """
        data = SnapshotJsonCodec.updated_data(contents, field_name, new_value)
        return SnapshotJsonCodec.encode_data(data, converter)

    @staticmethod
    def snapshot_data(snapshot: Snapshot) -> dict:
        """Validate before conversion, preserving public serializer hook timing."""
        snapshot.validate()
        data = asdict(snapshot)
        for association_data, association in zip(data["directories"], snapshot.directories):
            association_data["storage_name"] = association.directory_name
        return data

    @staticmethod
    def updated_data(contents: str, field_name: str, new_value) -> dict:
        """Patch a decoded JSON object without constructing a domain model."""
        data = json.loads(contents)
        data[field_name] = new_value
        return data

    @staticmethod
    def encode_data(data: dict, converter: Callable | None = None) -> str:
        """Encode prepared data with the existing converter and indentation."""
        return json.dumps(data, default=converter if converter is not None else SnapshotJsonCodec.convert, indent=4)


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
