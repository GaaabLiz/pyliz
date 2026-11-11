"""Compatibility facade over JSON conversion and protected metadata file access."""

from pathlib import Path

from pylizlib.core.os.snap.domain import Snapshot
from pylizlib.core.os.snap.storage.metadata import MetadataFile, SnapshotJsonCodec
from pylizlib.core.os.snap.storage.tree import is_link_or_junction


class SnapshotSerializer:
    """Compatible JSON facade preserving class hooks and protected metadata I/O.

    The codec owns conversion, MetadataFile owns descriptor safety, and this
    facade keeps hook resolution and file access in their original order."""

    @staticmethod
    def _is_link_or_junction(path: Path) -> bool:
        """Retain the legacy entry point for the shared symlink/junction check."""
        return is_link_or_junction(path)

    @staticmethod
    def _open_file(path: Path, flags: int, mode: int = 0o666) -> int:
        """Open a metadata file without following a replaced directory or link."""
        return MetadataFile.open_file(path, flags, mode)

    @classmethod
    def read_bytes(cls, path: Path) -> bytes:
        """Read a regular metadata file without following symbolic links."""
        return MetadataFile.read_bytes(path, opener=cls._open_file)

    @classmethod
    def read_text(cls, path: Path) -> str:
        """Decode protected metadata bytes as UTF-8 using the class read hook."""
        return cls.read_bytes(path).decode("utf-8")

    @classmethod
    def write_bytes(cls, path: Path, contents: bytes) -> None:
        """Write a regular metadata file without following symbolic links."""
        return MetadataFile.write_bytes(path, contents, opener=cls._open_file)

    @classmethod
    def write_text(cls, path: Path, contents: str) -> None:
        """Encode UTF-8 and invoke the class byte-write hook without adding a newline."""
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
        return SnapshotJsonCodec.convert(o)

    @staticmethod
    def to_json(snapshot: Snapshot, path: Path) -> None:
        """
        Serializes a Snapshot object to a JSON file.

        Args:
            snapshot: The Snapshot object to serialize.
            path: The file path where the JSON data will be saved.
        """
        data_dict = SnapshotJsonCodec.snapshot_data(snapshot)
        json_str = SnapshotJsonCodec.encode_data(data_dict, SnapshotSerializer._converter)
        SnapshotSerializer.write_text(path, json_str)

    @classmethod
    def from_json(cls, filepath: Path) -> Snapshot:
        """Reads a Snapshot from a JSON file, converting datetimes and enums."""
        return SnapshotJsonCodec.decode(cls.read_text(filepath))

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
        data = SnapshotJsonCodec.updated_data(cls.read_text(filepath), field_name, new_value)
        json_str = SnapshotJsonCodec.encode_data(data, cls._converter)
        cls.write_text(filepath, json_str)
