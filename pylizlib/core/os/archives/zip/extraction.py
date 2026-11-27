"""Extract validated ZIP members with per-device capacity checks."""

import os
import stat
import zipfile
from collections.abc import Iterable
from pathlib import Path

from pylizlib.core.os.archives.zip.validation import DEFAULT_MAX_ARCHIVE_ENTRIES, DEFAULT_MAX_ARCHIVE_UNCOMPRESSED_BYTES, validate_zip_archive
from pylizlib.core.os.filesystem.capacity import ensure_required_space
from pylizlib.core.os.paths.safety import assert_no_link_components


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
    function returns must not be mistaken for extraction failures. On POSIX,
    Unix ZIP file entries retain their executable bits.

    Args:
        zip_path (Path): ZIP whose complete member table is validated first.
        destination (Path): Extraction directory, created after successful validation.
        max_entries (int | None): Maximum members; None disables the limit.
        max_uncompressed_bytes (int | None): Maximum expanded bytes; None disables it.
        additional_space_paths (Iterable[Path]): Existing directories requiring a simultaneous full-size copy of
            the expanded archive.
        additional_space_requirements (Iterable[tuple[Path, int]]): Explicit additional byte requirements, summed
            with the full-copy requirements.

    Returns:
        None: On extraction success; the caller owns the extracted tree and cleanup.

    Raises:
        ValueError: If ZIP structure, members or resource bounds are invalid.
        OSError: If capacity checks, I/O or decompression fails. The exception message identifies extraction; a
            partial destination may remain.
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
        ensure_required_space(destination, preflight.uncompressed_bytes, requirements)
        with zipfile.ZipFile(zip_path, "r") as archive:
            archive.extractall(destination)
            if os.name != "posix":
                return

            destination = destination.resolve()
            for member in archive.infolist():
                executable_bits = (member.external_attr >> 16) & 0o111
                if member.create_system != 3 or member.is_dir() or not executable_bits:
                    continue

                extracted = destination / member.filename
                assert_no_link_components(extracted)
                rw_bits = stat.S_IMODE(extracted.stat(follow_symlinks=False).st_mode) & 0o666
                extracted.chmod(rw_bits | executable_bits, follow_symlinks=False)
    except zipfile.BadZipFile:
        raise ValueError(f"File '{zip_path}' is not a valid zip file.")
    except ValueError:
        raise
    except Exception as e:
        raise IOError(f"Failed to extract zip file '{zip_path}': {e}")
