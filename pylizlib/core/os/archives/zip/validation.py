"""ZIP member validation and expansion limits before extraction."""

import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

DEFAULT_MAX_ARCHIVE_UNCOMPRESSED_BYTES = 100 * 1024 * 1024 * 1024
DEFAULT_MAX_ARCHIVE_ENTRIES = 1_000_000


@dataclass(frozen=True)
class ZipArchivePreflight:
    """Describe validated ZIP expansion without extracting any content.

    Attributes:
        entry_count (int): Number of members, including explicit directory entries.
        uncompressed_bytes (int): Sum of the members' declared expanded byte sizes.
        bytes_by_root (dict[str, int]): Expanded sizes grouped by first path component. The dictionary is mutable
            even though the record fields are frozen.
    """

    entry_count: int
    uncompressed_bytes: int
    bytes_by_root: dict[str, int]


def validate_zip_archive(
    zip_path: Path,
    *,
    max_entries: int | None = DEFAULT_MAX_ARCHIVE_ENTRIES,
    max_uncompressed_bytes: int | None = DEFAULT_MAX_ARCHIVE_UNCOMPRESSED_BYTES,
) -> ZipArchivePreflight:
    """Validate member paths and resource bounds without extracting the archive.

    Args:
        zip_path (Path): ZIP to inspect. The member table is read into memory.
        max_entries (int | None): Maximum members, or None to disable this bound.
        max_uncompressed_bytes (int | None): Maximum declared expanded bytes, or None to disable this bound.
            Equality with either limit is allowed.

    Returns:
        ZipArchivePreflight: Counts and sizes for accepted members.

    Raises:
        ValueError: If the ZIP is invalid or a member is absolute, ambiguous, duplicate, encrypted, a symbolic
            link, or exceeds a resource bound.
        OSError: If inspection fails for another reason, with the cause chained.

    Notes:
        This validates declared structure and sizes, not CRCs or authenticity.
    """

    # Read the complete member table before creating any extraction destination.
    try:
        with zipfile.ZipFile(zip_path, "r") as archive:
            infos = archive.infolist()
    except zipfile.BadZipFile as error:
        raise ValueError(f"File '{zip_path}' is not a valid zip file.") from error
    except ValueError:
        raise
    except Exception as error:
        raise IOError(f"Failed to inspect zip file '{zip_path}': {error}") from error

    if max_entries is not None and len(infos) > max_entries:
        raise ValueError(f"Archive contains {len(infos)} entries; configured limit is {max_entries}.")

    # Track normalized member uniqueness and cumulative expanded size in archive order.
    total_bytes = 0
    bytes_by_root = {}
    seen_paths = set()
    for info in infos:
        name = info.filename
        if not name or "\\" in name or "\x00" in name:
            raise ValueError(f"Archive contains an invalid member path: {name!r}.")
        raw_components = name.rstrip("/").split("/")
        posix_path = PurePosixPath(name.rstrip("/"))
        windows_path = PureWindowsPath(name)
        if posix_path.is_absolute() or windows_path.is_absolute() or windows_path.drive or any(part in {"", ".", ".."} or ":" in part for part in raw_components):
            raise ValueError(f"Archive member path escapes its extraction directory: {name!r}.")
        normalized_name = posix_path.as_posix()
        if normalized_name in {"", "."}:
            raise ValueError(f"Archive contains an invalid member path: {name!r}.")
        if normalized_name in seen_paths:
            raise ValueError(f"Archive contains duplicate member path '{normalized_name}'.")
        seen_paths.add(normalized_name)

        # Reject links and encrypted members before trusting their expansion totals.
        unix_mode = (info.external_attr >> 16) & 0xFFFF
        if info.create_system == 3 and stat.S_ISLNK(unix_mode):
            raise ValueError(f"Archive member '{name}' is a symbolic link.")
        if info.flag_bits & 0x1:
            raise ValueError(f"Archive member '{name}' is encrypted and cannot be imported.")
        if info.file_size < 0:
            raise ValueError(f"Archive member '{name}' has an invalid uncompressed size.")
        total_bytes += info.file_size
        root_name = raw_components[0]
        bytes_by_root[root_name] = bytes_by_root.get(root_name, 0) + info.file_size
        if max_uncompressed_bytes is not None and total_bytes > max_uncompressed_bytes:
            raise ValueError(f"Archive expands to more than the configured limit of {max_uncompressed_bytes} bytes.")
    return ZipArchivePreflight(len(infos), total_bytes, bytes_by_root)
