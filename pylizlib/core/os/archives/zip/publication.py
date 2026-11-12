"""Create and verify ZIP files before publishing a final archive name."""

import tempfile
import zipfile
from collections.abc import Iterable
from pathlib import Path

from pylizlib.core.log.pylizLogger import logger


def write_verified_zip(zip_path: Path, files: Iterable[tuple[Path, Path]], message_callback=None) -> Path:
    """Publish a ZIP after complete enumeration, close and CRC verification.

    Args:
        zip_path (Path): Final archive path; an existing entry may be replaced.
        files (Iterable[tuple[Path, Path]]): Source entries and relative archive names. The iterable is fully
            consumed before the temporary ZIP is created.
        message_callback (Callable[[str], None] | None): Optional observer called before each member is archived;
            its exceptions propagate.

    Returns:
        Path: The final ZIP path after publication.

    Raises:
        OSError: If enumeration, writing or atomic replacement fails.
        zipfile.BadZipFile: If a member fails the post-close CRC check.

    Notes:
        Member-name policy belongs to the caller; use validation before extracting. CRC verification is not
        authentication or a guarantee of storage durability.
    """
    return _write_verified_zip(zip_path, files, message_callback, replace_existing=True)


def write_verified_zip_exclusive(zip_path: Path, files: Iterable[tuple[Path, Path]], message_callback=None) -> Path:
    """Publish a verified ZIP using an exclusive same-filesystem hard link.

    Args:
        zip_path (Path): Final path, which must not already exist.
        files (Iterable[tuple[Path, Path]]): Source entries and relative archive names.
        message_callback (Callable[[str], None] | None): Optional per-member observer.

    Returns:
        Path: Published ZIP path, after the temporary archive has passed CRC checks.

    Raises:
        FileExistsError: If another entry already occupies the final name.
        OSError: If writing or hard-link publication fails.
        zipfile.BadZipFile: If CRC verification fails.
    """
    return _write_verified_zip(zip_path, files, message_callback, replace_existing=False)


def _write_verified_zip(zip_path: Path, files: Iterable[tuple[Path, Path]], message_callback, *, replace_existing: bool) -> Path:
    """Write one sibling temporary ZIP and publish it with the selected policy.

    Args:
        zip_path (Path): Final path and parent used for same-filesystem staging.
        files (Iterable[tuple[Path, Path]]): Source entries and member names.
        message_callback (Callable[[str], None] | None): Per-member observer.
        replace_existing (bool): Replace the final entry when True, otherwise link exclusively. Cleanup errors are
            logged without hiding the main result.

    Returns:
        Path: Final path after CRC verification and publication.

    Raises:
        OSError: If writing or publication fails.
        zipfile.BadZipFile: If a completed archive fails CRC verification.
    """
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

        # A same-filesystem hard link is atomic and fails with EEXIST if a
        # concurrent writer already published this name. Unlike replace(),
        # it cannot truncate a completed backup.
        else:
            zip_path.hardlink_to(temporary_path)
        return zip_path
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError as e:
                logger.warning(f"Could not remove unfinished backup '{temporary_path}': {e}")
