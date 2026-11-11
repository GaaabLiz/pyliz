"""Snapshot JSON conversion and protected metadata file access."""

import json
import os
import stat
from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime
from enum import Enum
from pathlib import Path

from pylizlib.core.os.snap.domain import SnapDirAssociation, Snapshot, validate_directory_component
from pylizlib.core.os.snap.storage.tree import is_link_or_junction


class MetadataFile:
    """Read and rewrite regular metadata files without following replaced links.

    Writes retain the original open/verify/truncate behavior. They do not add
    atomic replacement, locking, or durability guarantees. The optional opener
    allows the public serializer's class hooks to remain effective.
    """

    @staticmethod
    def open_file(path: Path, flags: int, mode: int = 0o666) -> int:
        """Open a metadata file without following a replaced directory or link."""
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        directory = getattr(os, "O_DIRECTORY", 0)
        parent_before = path.parent.lstat()
        if not stat.S_ISDIR(parent_before.st_mode) or is_link_or_junction(path.parent):
            raise ValueError(f"Snapshot metadata directory '{path.parent}' is not a real directory.")

        if nofollow and directory and os.open in os.supports_dir_fd:
            parent_fd = os.open(path.parent, os.O_RDONLY | directory | nofollow)
            try:
                if not os.path.samestat(parent_before, os.fstat(parent_fd)):
                    raise ValueError(f"Snapshot metadata directory '{path.parent}' changed while opening it.")
                return os.open(path.name, flags | nofollow, mode, dir_fd=parent_fd)
            finally:
                os.close(parent_fd)

        try:
            file_before = path.lstat()
        except FileNotFoundError:
            file_before = None
        if file_before is not None and (not stat.S_ISREG(file_before.st_mode) or is_link_or_junction(path)):
            raise ValueError(f"Snapshot metadata path '{path}' cannot be a symbolic link.")

        descriptor = os.open(path, flags | nofollow, mode)
        try:
            parent_after = path.parent.lstat()
            file_after = path.lstat()
            opened_file = os.fstat(descriptor)
            if not stat.S_ISDIR(parent_after.st_mode) or is_link_or_junction(path.parent) or not os.path.samestat(parent_before, parent_after):
                raise ValueError(f"Snapshot metadata directory '{path.parent}' changed while opening it.")
            if not stat.S_ISREG(opened_file.st_mode) or not os.path.samestat(opened_file, file_after) or (file_before is not None and not os.path.samestat(file_before, file_after)):
                raise ValueError(f"Snapshot metadata path '{path}' changed while opening it.")
            return descriptor
        except Exception:
            os.close(descriptor)
            raise

    @staticmethod
    def read_bytes(path: Path, opener: Callable = None) -> bytes:
        """Read a regular metadata file without following symbolic links."""
        descriptor = (opener if opener is not None else MetadataFile.open_file)(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise ValueError(f"Snapshot metadata path '{path}' is not a regular file.")
            with os.fdopen(descriptor, "rb", closefd=False) as file:
                return file.read()
        finally:
            os.close(descriptor)

    @staticmethod
    def write_bytes(path: Path, contents: bytes, opener: Callable = None) -> None:
        """Write a regular metadata file without following symbolic links."""
        descriptor = (opener if opener is not None else MetadataFile.open_file)(path, os.O_WRONLY | os.O_CREAT | getattr(os, "O_NONBLOCK", 0))
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise ValueError(f"Snapshot metadata path '{path}' is not a regular file.")
            os.ftruncate(descriptor, 0)
            with os.fdopen(descriptor, "wb", closefd=False) as file:
                file.write(contents)
                file.flush()
        finally:
            os.close(descriptor)


class SnapshotJsonCodec:
    """Convert snapshot metadata in memory without choosing a file I/O policy.

    Decoding retains legacy defaults and invokes the domain constructors, whose
    size calculation and validation side effects remain part of compatibility.
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
        ]:
            if key in data and data[key] is not None:
                data[key] = datetime.fromisoformat(data[key])

        # Convert 'directories' into a list of SnapDirAssociation
        if "directories" in data and isinstance(data["directories"], list):
            if any(not isinstance(directory, dict) for directory in data["directories"]):
                raise ValueError("Snapshot JSON directories must contain objects.")
            data["directories"] = [SnapDirAssociation(**directory) for directory in data["directories"]]
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
        return asdict(snapshot)

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
