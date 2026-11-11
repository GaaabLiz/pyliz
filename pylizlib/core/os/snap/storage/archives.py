"""Verified ZIP publication independent of snapshot archive conventions."""

import tempfile
import zipfile
from collections.abc import Iterable
from pathlib import Path

from pylizlib.core.log.pylizLogger import logger


def write_verified_zip(zip_path: Path, files: Iterable[tuple[Path, Path]], message_callback=None) -> Path:
    """Publish an archive only after complete enumeration and CRC verification."""
    temporary_path = None
    try:
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        # Complete enumeration before creating any archive in the source tree.
        entries = list(files)
        with tempfile.NamedTemporaryFile(dir=zip_path.parent, prefix=".backup_", suffix=".partial", delete=False) as temporary_file:
            temporary_path = Path(temporary_file.name)
        with zipfile.ZipFile(temporary_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for source, archive_name in entries:
                if message_callback:
                    message_callback(f"Archiviazione: {source.name}")
                archive.write(source, arcname=archive_name)
        # Reopen after close: finalization can fail, and each member must
        # pass its CRC check before the normal filename becomes visible.
        with zipfile.ZipFile(temporary_path, "r") as archive:
            corrupted_member = archive.testzip()
            if corrupted_member is not None:
                raise zipfile.BadZipFile(f"Backup validation failed for '{corrupted_member}'.")
        temporary_path.replace(zip_path)
        return zip_path
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError as e:
                logger.warning(f"Could not remove unfinished backup '{temporary_path}': {e}")


def extract_zip(zip_path: Path, destination: Path) -> None:
    """Extract members with the existing ZIP policy and public error mapping.

    The caller owns the temporary directory. Errors from the caller after this
    function returns must not be mistaken for extraction failures.
    """
    try:
        with zipfile.ZipFile(zip_path, "r") as archive:
            archive.extractall(destination)
    except zipfile.BadZipFile:
        raise ValueError(f"File '{zip_path}' is not a valid zip file.")
    except Exception as e:
        raise IOError(f"Failed to extract zip file '{zip_path}': {e}")
