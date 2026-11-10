"""
JSON serialization and deserialization for the Snapshot model.

Responsibilities (Single Responsibility Principle):
    - Converting a Snapshot object to a JSON file on disk.
    - Reconstructing a Snapshot object from a JSON file.
    - Updating a single field in an existing JSON file without a full round-trip.

Classes:
    SnapshotSerializer – Static helpers for snapshot JSON I/O.
"""

import json
import os
import stat
from dataclasses import asdict
from datetime import datetime
from enum import Enum
from pathlib import Path

from pylizlib.core.os.snap.domain import SnapDirAssociation, Snapshot


class SnapshotSerializer:
    @staticmethod
    def _is_link_or_junction(path: Path) -> bool:
        is_junction = getattr(path, "is_junction", None)
        return path.is_symlink() or (is_junction is not None and is_junction())

    @staticmethod
    def _open_file(path: Path, flags: int, mode: int = 0o666) -> int:
        """Open a metadata file without following a replaced directory or link."""
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        directory = getattr(os, "O_DIRECTORY", 0)
        parent_before = path.parent.lstat()
        if not stat.S_ISDIR(parent_before.st_mode) or SnapshotSerializer._is_link_or_junction(path.parent):
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
        if file_before is not None and (
            not stat.S_ISREG(file_before.st_mode) or SnapshotSerializer._is_link_or_junction(path)
        ):
            raise ValueError(f"Snapshot metadata path '{path}' cannot be a symbolic link.")

        descriptor = os.open(path, flags | nofollow, mode)
        try:
            parent_after = path.parent.lstat()
            file_after = path.lstat()
            opened_file = os.fstat(descriptor)
            if (
                not stat.S_ISDIR(parent_after.st_mode)
                or SnapshotSerializer._is_link_or_junction(path.parent)
                or not os.path.samestat(parent_before, parent_after)
            ):
                raise ValueError(f"Snapshot metadata directory '{path.parent}' changed while opening it.")
            if (
                not stat.S_ISREG(opened_file.st_mode)
                or not os.path.samestat(opened_file, file_after)
                or (file_before is not None and not os.path.samestat(file_before, file_after))
            ):
                raise ValueError(f"Snapshot metadata path '{path}' changed while opening it.")
            return descriptor
        except Exception:
            os.close(descriptor)
            raise

    @classmethod
    def read_bytes(cls, path: Path) -> bytes:
        """Read a regular metadata file without following symbolic links."""
        descriptor = cls._open_file(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise ValueError(f"Snapshot metadata path '{path}' is not a regular file.")
            with os.fdopen(descriptor, "rb", closefd=False) as file:
                return file.read()
        finally:
            os.close(descriptor)

    @classmethod
    def read_text(cls, path: Path) -> str:
        return cls.read_bytes(path).decode("utf-8")

    @classmethod
    def write_bytes(cls, path: Path, contents: bytes) -> None:
        """Write a regular metadata file without following symbolic links."""
        descriptor = cls._open_file(path, os.O_WRONLY | os.O_CREAT | getattr(os, "O_NONBLOCK", 0))
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise ValueError(f"Snapshot metadata path '{path}' is not a regular file.")
            os.ftruncate(descriptor, 0)
            with os.fdopen(descriptor, "wb", closefd=False) as file:
                file.write(contents)
                file.flush()
        finally:
            os.close(descriptor)

    @classmethod
    def write_text(cls, path: Path, contents: str) -> None:
        cls.write_bytes(path, contents.encode("utf-8"))

    @staticmethod
    def _converter(o):
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
    def to_json(snapshot: Snapshot, path: Path) -> None:
        """
        Serializes a Snapshot object to a JSON file.

        Args:
            snapshot: The Snapshot object to serialize.
            path: The file path where the JSON data will be saved.
        """
        snapshot.validate()
        data_dict = asdict(snapshot)
        json_str = json.dumps(data_dict, default=SnapshotSerializer._converter, indent=4)
        SnapshotSerializer.write_text(path, json_str)

    @classmethod
    def from_json(cls, filepath: Path) -> Snapshot:
        """Reads a Snapshot from a JSON file, converting datetimes and enums."""
        data = json.loads(cls.read_text(filepath))
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

    @classmethod
    def update_field(
        cls,
        filepath: Path,
        field_name: str,
        new_value,
    ):
        """
        Updates a single field in a snapshot's JSON file without loading the whole object.

        Args:
            filepath: The path to the JSON file.
            field_name: The name of the field to update.
            new_value: The new value for the field.
        """
        # Read existing data from the JSON file
        data = json.loads(cls.read_text(filepath))

        # Update only the specified field
        data[field_name] = new_value

        # Serialize the file again with converters for datetime and enum if necessary
        json_str = json.dumps(data, default=cls._converter, indent=4)
        cls.write_text(filepath, json_str)
