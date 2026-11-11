"""Snapshot JSON conversion and protected metadata file access."""

import errno
import json
import os
import secrets
import stat
from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime
from enum import Enum
from pathlib import Path

from pylizlib.core.log.pylizLogger import logger
from pylizlib.core.os.snap.domain import SnapDirAssociation, Snapshot, validate_directory_component
from pylizlib.core.os.snap.storage.tree import is_link_or_junction


class MetadataDurabilityError(OSError):
    """The new metadata name was published, but its directory flush failed."""

    def __init__(self, path: Path, cause: OSError):
        """Record that atomic publication succeeded while durability is unknown."""
        super().__init__(f"Metadata '{path}' was published atomically, but storage durability could not be confirmed: {cause}")
        self.path = Path(path)
        self.published = True
        self.durability_confirmed = False


class MetadataFile:
    """Read metadata safely and publish writes through same-directory staging.

    Successful writes fsync the staged file before atomically replacing the
    current name, and retain the previous bytes in a hidden sidecar. Parent
    directory fsync is attempted where supported. A successful fsync request
    cannot prove that a remote server has committed data to stable media.
    """

    _UNSUPPORTED_DIRECTORY_SYNC = {
        errno.EBADF,
        errno.EINVAL,
        getattr(errno, "ENOTSUP", errno.EINVAL),
        getattr(errno, "EOPNOTSUPP", errno.EINVAL),
    }

    @staticmethod
    def previous_path(path: Path) -> Path:
        """Return the hidden sibling that holds the last published version."""
        path = Path(path)
        return path.with_name(f".{path.name}.previous")

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
    def _regular_file_stat(path: Path) -> os.stat_result | None:
        """Return lstat data for an absent or regular file, rejecting links."""
        try:
            file_stat = path.lstat()
        except FileNotFoundError:
            return None
        if not stat.S_ISREG(file_stat.st_mode) or is_link_or_junction(path):
            raise ValueError(f"Snapshot metadata path '{path}' must be a regular file.")
        return file_stat

    @staticmethod
    def _temporary_path(path: Path) -> Path:
        """Choose an uncreated, unpredictable temporary sibling name."""
        return path.with_name(f".{path.name}.{secrets.token_hex(12)}.tmp")

    @staticmethod
    def _write_temporary(path: Path, contents: bytes, opener: Callable, mode: int, *, preserve_mode: bool) -> None:
        """Create, write and fsync one temporary metadata file."""
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NONBLOCK", 0)
        descriptor = opener(path, flags, mode)
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise ValueError(f"Snapshot temporary metadata path '{path}' is not a regular file.")
            if preserve_mode and os.name != "nt" and hasattr(os, "fchmod"):
                os.fchmod(descriptor, mode)
            with os.fdopen(descriptor, "wb", closefd=False) as file:
                written = file.write(contents)
                if written != len(contents):
                    raise OSError(f"Short write while preparing metadata '{path}'.")
                file.flush()
                os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @staticmethod
    def _same_parent(path: Path, expected: os.stat_result) -> bool:
        """Check the destination directory identity and link status."""
        current = path.parent.lstat()
        return stat.S_ISDIR(current.st_mode) and not is_link_or_junction(path.parent) and os.path.samestat(expected, current)

    @classmethod
    def _replace_sibling(cls, source: Path, destination: Path, expected_parent: os.stat_result) -> None:
        """Replace a sibling entry, anchoring the rename to a directory FD where available."""
        if not cls._same_parent(destination, expected_parent):
            raise ValueError(f"Snapshot metadata directory '{destination.parent}' changed before publication.")

        directory_flag = getattr(os, "O_DIRECTORY", 0)
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        if directory_flag and os.replace in os.supports_dir_fd:
            parent_fd = os.open(destination.parent, os.O_RDONLY | directory_flag | nofollow)
            try:
                if not os.path.samestat(expected_parent, os.fstat(parent_fd)):
                    raise ValueError(f"Snapshot metadata directory '{destination.parent}' changed before publication.")
                os.replace(source.name, destination.name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
            finally:
                os.close(parent_fd)
        else:
            os.replace(source, destination)

    @classmethod
    def _sync_parent_directory(cls, path: Path, expected_parent: os.stat_result) -> bool:
        """Request persistence of a directory entry; return False if unsupported."""
        directory_flag = getattr(os, "O_DIRECTORY", 0)
        if not directory_flag:
            return False

        try:
            parent_fd = os.open(path.parent, os.O_RDONLY | directory_flag | getattr(os, "O_NOFOLLOW", 0))
        except OSError as error:
            if os.name == "nt" or error.errno in cls._UNSUPPORTED_DIRECTORY_SYNC:
                return False
            raise

        try:
            if not os.path.samestat(expected_parent, os.fstat(parent_fd)):
                raise OSError(f"Snapshot metadata directory '{path.parent}' changed before directory sync.")
            try:
                os.fsync(parent_fd)
            except OSError as error:
                if error.errno in cls._UNSUPPORTED_DIRECTORY_SYNC:
                    return False
                raise
            return True
        finally:
            os.close(parent_fd)

    @classmethod
    def write_bytes(cls, path: Path, contents: bytes, opener: Callable = None) -> None:
        """Atomically replace a regular metadata file and preserve its prior bytes.

        The temporary and previous-version files are created beside ``path``.
        Errors before replacing ``path`` leave the current version untouched.
        A :class:`MetadataDurabilityError` means replacement succeeded but the
        final parent-directory fsync failed. Network servers may acknowledge
        flushes without guaranteeing physical-media persistence.
        """
        path = Path(path)
        if not isinstance(contents, bytes):
            raise TypeError("Metadata contents must be bytes.")
        opener = opener if opener is not None else MetadataFile.open_file
        parent_stat = path.parent.lstat()
        if not stat.S_ISDIR(parent_stat.st_mode) or is_link_or_junction(path.parent):
            raise ValueError(f"Snapshot metadata directory '{path.parent}' is not a real directory.")

        current_stat = cls._regular_file_stat(path)
        previous_bytes = None
        if current_stat is not None:
            previous_bytes = cls.read_bytes(path, opener=opener)
            after_read_stat = cls._regular_file_stat(path)
            if after_read_stat is None or not os.path.samestat(current_stat, after_read_stat) or (
                current_stat.st_size != after_read_stat.st_size or current_stat.st_mtime_ns != after_read_stat.st_mtime_ns
            ):
                raise OSError(f"Snapshot metadata '{path}' changed while preparing its replacement.")

        previous_path = cls.previous_path(path)
        cls._regular_file_stat(previous_path)
        new_temp = cls._temporary_path(path)
        previous_temp = cls._temporary_path(previous_path) if previous_bytes is not None else None
        try:
            file_mode = stat.S_IMODE(current_stat.st_mode) if current_stat is not None else 0o666
            cls._write_temporary(new_temp, contents, opener, file_mode, preserve_mode=current_stat is not None)

            if previous_bytes is not None:
                previous_mode = stat.S_IMODE(current_stat.st_mode)
                assert previous_temp is not None
                cls._write_temporary(previous_temp, previous_bytes, opener, previous_mode, preserve_mode=True)
                cls._replace_sibling(previous_temp, previous_path, parent_stat)
                previous_temp = None
                cls._sync_parent_directory(path, parent_stat)

            # Recheck the target to reject a link or type substitution immediately
            # before the atomic publication step.
            cls._regular_file_stat(path)
            cls._replace_sibling(new_temp, path, parent_stat)
            new_temp = None
            try:
                directory_synced = cls._sync_parent_directory(path, parent_stat)
            except OSError as error:
                raise MetadataDurabilityError(path, error) from error
            if not directory_synced:
                logger.warning(
                    f"Metadata '{path}' was atomically published, but parent-directory durability is unavailable."
                )
        finally:
            for temporary_path in (new_temp, previous_temp):
                if temporary_path is not None:
                    try:
                        temporary_path.unlink(missing_ok=True)
                    except OSError as error:
                        logger.warning(f"Could not remove metadata staging file '{temporary_path}': {error}")


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
