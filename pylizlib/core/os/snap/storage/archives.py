"""Verified ZIP publication independent of snapshot archive conventions."""

import errno
import shutil
import stat
import tempfile
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

from pylizlib.core.log.pylizLogger import logger
from pylizlib.core.os.snap.storage.archive_limits import DEFAULT_MAX_ARCHIVE_ENTRIES, DEFAULT_MAX_ARCHIVE_UNCOMPRESSED_BYTES


@dataclass(frozen=True)
class ZipArchivePreflight:
    """Validated entry counts and expanded byte totals grouped by top-level path."""

    entry_count: int
    uncompressed_bytes: int
    bytes_by_root: dict[str, int]


def write_verified_zip(zip_path: Path, files: Iterable[tuple[Path, Path]], message_callback=None) -> Path:
    """Publish an archive only after complete enumeration and CRC verification."""
    return _write_verified_zip(zip_path, files, message_callback, replace_existing=True)


def _write_verified_zip_exclusive(zip_path: Path, files: Iterable[tuple[Path, Path]], message_callback=None) -> Path:
    """Publish a verified archive atomically without replacing an existing path."""
    return _write_verified_zip(zip_path, files, message_callback, replace_existing=False)


def _write_verified_zip(zip_path: Path, files: Iterable[tuple[Path, Path]], message_callback, *, replace_existing: bool) -> Path:
    """Write a verified ZIP to a sibling temporary file before publication."""
    temporary_path = None
    try:
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        # Complete enumeration before creating any archive in the source tree.
        entries = files if isinstance(files, list) else list(files)
        with tempfile.NamedTemporaryFile(dir=zip_path.parent, prefix=".backup_", suffix=".partial", delete=False) as temporary_file:
            temporary_path = Path(temporary_file.name)
        with zipfile.ZipFile(temporary_path, "w", zipfile.ZIP_DEFLATED, strict_timestamps=False) as archive:
            for source, archive_name in entries:
                if message_callback:
                    message_callback(f"Archiviazione: {source.name}")
                archive_name = Path(archive_name).as_posix()
                if source.is_dir() and not archive_name.endswith("/"):
                    archive_name += "/"
                archive.write(source, arcname=archive_name)
        # Reopen after close: finalization can fail, and each member must
        # pass its CRC check before the normal filename becomes visible.
        with zipfile.ZipFile(temporary_path, "r") as archive:
            corrupted_member = archive.testzip()
            if corrupted_member is not None:
                raise zipfile.BadZipFile(f"Backup validation failed for '{corrupted_member}'.")
        if replace_existing:
            temporary_path.replace(zip_path)
        else:
            # A same-filesystem hard link is atomic and fails with EEXIST if a
            # concurrent writer already published this name. Unlike replace(),
            # it cannot truncate a completed backup.
            zip_path.hardlink_to(temporary_path)
        return zip_path
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError as e:
                logger.warning(f"Could not remove unfinished backup '{temporary_path}': {e}")


def validate_zip_archive(
    zip_path: Path,
    *,
    max_entries: int | None = DEFAULT_MAX_ARCHIVE_ENTRIES,
    max_uncompressed_bytes: int | None = DEFAULT_MAX_ARCHIVE_UNCOMPRESSED_BYTES,
) -> ZipArchivePreflight:
    """Validate member paths and resource bounds, returning expanded byte totals."""
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
        if (
            posix_path.is_absolute()
            or windows_path.is_absolute()
            or windows_path.drive
            or any(part in {"", ".", ".."} or ":" in part for part in raw_components)
        ):
            raise ValueError(f"Archive member path escapes its extraction directory: {name!r}.")
        normalized_name = posix_path.as_posix()
        if normalized_name in {"", "."}:
            raise ValueError(f"Archive contains an invalid member path: {name!r}.")
        if normalized_name in seen_paths:
            raise ValueError(f"Archive contains duplicate member path '{normalized_name}'.")
        seen_paths.add(normalized_name)

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
            raise ValueError(
                f"Archive expands to more than the configured limit of {max_uncompressed_bytes} bytes."
            )
    return ZipArchivePreflight(len(infos), total_bytes, bytes_by_root)


def _ensure_required_space(
    extraction_path: Path,
    extraction_bytes: int,
    additional_requirements: Iterable[tuple[Path, int]],
) -> None:
    """Check expanded and final-copy space per filesystem before extraction."""
    extraction_path = Path(extraction_path)
    if not extraction_path.is_dir():
        raise FileNotFoundError(f"Archive extraction directory '{extraction_path}' does not exist.")
    extraction_device = extraction_path.stat().st_dev
    per_device: dict[int, tuple[Path, int]] = {extraction_device: (extraction_path, extraction_bytes)}
    additional_by_device: dict[int, tuple[Path, int]] = {}
    for path, required_bytes in additional_requirements:
        path = Path(path)
        if not path.is_dir():
            raise FileNotFoundError(f"Required extraction or publish directory '{path}' does not exist.")
        device = path.stat().st_dev
        existing_path, existing_required = additional_by_device.get(device, (path, 0))
        additional_by_device[device] = existing_path, existing_required + required_bytes

    for device, (path, required_bytes) in additional_by_device.items():
        existing = per_device.get(device)
        per_device[device] = (path, required_bytes) if existing is None else (existing[0], existing[1] + required_bytes)

    for path, required_bytes in per_device.values():
        available_bytes = shutil.disk_usage(path).free
        if available_bytes < required_bytes:
            raise OSError(
                errno.ENOSPC,
                f"Archive staging requires {required_bytes} bytes on '{path}', "
                f"but only {available_bytes} bytes are available.",
            )


def extract_zip(
    zip_path: Path,
    destination: Path,
    *,
    max_entries: int | None = DEFAULT_MAX_ARCHIVE_ENTRIES,
    max_uncompressed_bytes: int | None = DEFAULT_MAX_ARCHIVE_UNCOMPRESSED_BYTES,
    additional_space_paths: Iterable[Path] = (),
    additional_space_requirements: Iterable[tuple[Path, int]] = (),
) -> None:
    """Preflight and extract a ZIP with bounded resources and public error mapping.

    The caller owns the temporary directory. Errors from the caller after this
    function returns must not be mistaken for extraction failures.
    """
    try:
        preflight = validate_zip_archive(
            zip_path,
            max_entries=max_entries,
            max_uncompressed_bytes=max_uncompressed_bytes,
        )
        destination = Path(destination)
        destination.mkdir(parents=True, exist_ok=True)
        requirements = [(Path(path), preflight.uncompressed_bytes) for path in additional_space_paths]
        requirements.extend((Path(path), required) for path, required in additional_space_requirements)
        _ensure_required_space(destination, preflight.uncompressed_bytes, requirements)
        with zipfile.ZipFile(zip_path, "r") as archive:
            archive.extractall(destination)
    except zipfile.BadZipFile:
        raise ValueError(f"File '{zip_path}' is not a valid zip file.")
    except ValueError:
        raise
    except Exception as e:
        raise IOError(f"Failed to extract zip file '{zip_path}': {e}")
