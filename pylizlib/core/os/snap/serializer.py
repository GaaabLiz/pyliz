"""Compatibility facade over JSON conversion and protected metadata file access."""

from pathlib import Path

from pylizlib.core.os.snap.domain import Snapshot
from pylizlib.core.os.snap.storage.metadata import MetadataFile, SnapshotJsonCodec
from pylizlib.core.os.snap.storage.tree import is_link_or_junction


class SnapshotSerializer:
    """Compatible JSON facade preserving class hooks and protected metadata I/O.

    The codec owns conversion, MetadataFile owns descriptor safety and atomic
    publication, and this facade keeps hook resolution and file access in their
    original order. A successful atomic replace does not certify remote-server
    stable-media persistence.
    """

    @staticmethod
    def _is_link_or_junction(path: Path) -> bool:
        """Retain the legacy entry point for the shared symlink/junction check.

        Args:
            path (Path): Native filesystem entry operated on by this method.

        Returns:
            bool: Whether the entry is a symbolic link or Windows junction, including a dangling link.
        """
        return is_link_or_junction(path)

    @staticmethod
    def _open_file(path: Path, flags: int, mode: int = 0o666) -> int:
        """Open a metadata file without following a replaced directory or link.

        Args:
            path (Path): Native filesystem entry operated on by this method.
            flags (int): Native os.open flags; the protected opener adds supported no-follow flags.
            mode (int): Native file creation permissions, filtered by umask unless existing permissions are explicitly
                restored.

        Returns:
            int: Open native descriptor, owned by the caller and requiring close.
        """
        return MetadataFile.open_file(path, flags, mode)

    @classmethod
    def read_bytes(cls, path: Path) -> bytes:
        """Read a regular metadata file without following symbolic links.

        Args:
            path (Path): Native filesystem entry operated on by this method.

        Returns:
            bytes: Exact regular-file contents, without decoding or newline conversion.

        Raises:
            ValueError: If an opened entry is unsafe or not regular.
            OSError: If protected opening, reading or descriptor closing fails.

        Notes:
            Descriptor safety and link/parent identity checks are provided by MetadataFile. File access failures
            propagate; catalogue lookup decides separately whether a failed load should be logged and skipped.
        """
        return MetadataFile.read_bytes(path, opener=cls._open_file)

    @classmethod
    def read_text(cls, path: Path) -> str:
        """Decode protected metadata bytes as UTF-8 using the class read hook.

        Args:
            path (Path): Native filesystem entry operated on by this method.

        Returns:
            str: UTF-8-decoded protected file contents; no newline is appended or removed.

        Raises:
            UnicodeDecodeError: If the protected file contents are not UTF-8.
            OSError: If protected reading fails.

        Notes:
            UTF-8 decoding is strict. This method delegates through cls.read_bytes so serializer subclasses retain
            their existing protected-read hook.
        """
        return cls.read_bytes(path).decode("utf-8")

    @classmethod
    def write_bytes(cls, path: Path, contents: bytes) -> None:
        """Write a regular metadata file without following symbolic links.

        Args:
            path (Path): Native filesystem entry operated on by this method.
            contents (bytes): Complete file or JSON contents, using the annotated bytes/text type without implicit
                conversion.

        Returns:
            None: No return value.

        Raises:
            ValueError: If destination, parent or prior-version entry is unsafe.
            OSError: If staging, prior-version publication or replacement fails.
            MetadataDurabilityError: If the current name was replaced but its final directory flush failed.

        Notes:
            AtomicFile/MetadataFile use same-directory staging, fsync and a hidden previous-version sibling.
            MetadataDurabilityError means the new bytes are already visible but the final directory flush failed;
            published is True and durability_confirmed is False.
        """
        return MetadataFile.write_bytes(path, contents, opener=cls._open_file)

    @classmethod
    def write_text(cls, path: Path, contents: str) -> None:
        """Encode UTF-8 and invoke the class byte-write hook without adding a newline.

        Args:
            path (Path): Native filesystem entry operated on by this method.
            contents (str): Complete file or JSON contents, using the annotated bytes/text type without implicit
                conversion.

        Returns:
            None: No return value.

        Raises:
            OSError: If UTF-8 byte publication fails.
            MetadataDurabilityError: If publication succeeded but final directory flushing failed.

        Notes:
            UTF-8 is encoded without adding a newline, then cls.write_bytes is called. MetadataDurabilityError is a
            post-publication failure, not evidence that the old current version remains published.
        """
        cls.write_bytes(path, contents.encode("utf-8"))

    @staticmethod
    def _converter(o):
        """Converts non-serializable objects for JSON dumping.

        Args:
            o (object): The object to convert.

        Returns:
            object: A serializable representation of the object.

        Raises:
            TypeError: If the object type is not supported.
        """
        return SnapshotJsonCodec.convert(o)

    @staticmethod
    def to_json(snapshot: Snapshot, path: Path) -> None:
        """Serializes a Snapshot object to a JSON file.

        Args:
            snapshot (Snapshot): The Snapshot object to serialize.
            path (Path): The file path where the JSON data will be saved.

        Returns:
            None: No return value.

        Notes:
            Snapshot validation happens before converter/write-hook resolution. Full saves include physical
            association storage_name and use atomic publication with a previous-version sidecar.
        """
        data_dict = SnapshotJsonCodec.snapshot_data(snapshot)
        json_str = SnapshotJsonCodec.encode_data(data_dict, SnapshotSerializer._converter)
        SnapshotSerializer.write_text(path, json_str)

    @classmethod
    def from_json(cls, filepath: Path) -> Snapshot:
        """Reads a Snapshot from a JSON file, converting datetimes and enums.

        Args:
            filepath (Path): Metadata file path to read or update through the protected serializer.

        Returns:
            Snapshot: Validated Snapshot using legacy date/default handling; loading never scans source directories
                for sizes.

        Raises:
            ValueError: If JSON/date/path/domain data is malformed.
            OSError: If protected reading fails.

        Notes:
            Read/UTF-8/JSON errors and domain validation failures propagate. Legacy missing fields retain their
            existing defaults; stored source sizes are not measured by scanning original directories. On Windows,
            domain normalization can query drive mappings.
        """
        return SnapshotJsonCodec.decode(cls.read_text(filepath))

    @classmethod
    def update_field(
        cls,
        filepath: Path,
        field_name: str,
        new_value,
    ):
        """Updates a single field in a snapshot's JSON file without loading the whole object.

        Args:
            filepath (Path): The path to the JSON file.
            field_name (str): The name of the field to update.
            new_value (object): The new value for the field.

        Returns:
            None: No return value.

        Raises:
            ValueError: If existing JSON is invalid or a protected entry is unsafe.
            OSError: If reading or atomic publication fails.
            MetadataDurabilityError: If the changed JSON was published but final directory flushing failed.

        Notes:
            This patches one raw JSON object field without validating the complete domain model, retaining unknown
            fields. Atomic file publication and the previous-version sidecar still apply.

            A successful write retains the immediately previous bytes in a hidden sibling. Read/decode/encode and
            atomic-write failures propagate, including MetadataDurabilityError after publication. No complete Snapshot
            validation is added to this raw-field API.
        """

        # Read existing data from the JSON file
        data = SnapshotJsonCodec.updated_data(cls.read_text(filepath), field_name, new_value)
        json_str = SnapshotJsonCodec.encode_data(data, cls._converter)
        cls.write_text(filepath, json_str)
