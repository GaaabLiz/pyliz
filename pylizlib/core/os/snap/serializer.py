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
from dataclasses import asdict
from datetime import datetime
from enum import Enum
from pathlib import Path

from pylizlib.core.os.snap.domain import Snapshot, SnapDirAssociation


class SnapshotSerializer:
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
        data_dict = asdict(snapshot)
        json_str = json.dumps(data_dict, default=SnapshotSerializer._converter, indent=4)
        path.write_text(json_str, encoding="utf-8")

    @classmethod
    def from_json(cls, filepath: Path) -> Snapshot:
        """Reads a Snapshot from a JSON file, converting datetimes and enums."""
        data = json.loads(filepath.read_text(encoding="utf-8"))

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
            data["directories"] = [SnapDirAssociation(**d) if isinstance(d, dict) else d for d in data["directories"]]

        return Snapshot(**data)

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
        data = json.loads(filepath.read_text(encoding="utf-8"))

        # Update only the specified field
        data[field_name] = new_value

        # Serialize the file again with converters for datetime and enum if necessary
        json_str = json.dumps(data, default=cls._converter, indent=4)
        filepath.write_text(json_str, encoding="utf-8")
