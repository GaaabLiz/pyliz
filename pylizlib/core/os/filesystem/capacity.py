"""Check cumulative byte requirements on each destination filesystem."""

import errno
import os
import shutil
from collections.abc import Iterable
from pathlib import Path

from pylizlib.core.log.pylizLogger import logger


def ensure_required_space(
    extraction_path: Path,
    extraction_bytes: int,
    additional_requirements: Iterable[tuple[Path, int]],
) -> None:
    """Sum simultaneous staging requirements per device and check free space.

    Args:
        extraction_path (Path): Existing directory receiving the initial expansion.
        extraction_bytes (int): Bytes required for that expansion.
        additional_requirements (Iterable[tuple[Path, int]]): Existing directories and additional bytes retained
            simultaneously, including final copies.

    Returns:
        None: If each device currently has at least its cumulative requirement.

    Raises:
        FileNotFoundError: If a required directory is absent or is not a directory.
        OSError: If stat/disk usage fails, or ENOSPC when a device lacks space.

    Notes:
        Space is observed, not reserved against concurrent writers. Byte counts are supplied by the caller and are
        not rounded to allocation units.
    """
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
        logger.debug("Capacity check: device_path=%s required_bytes=%s available_bytes=%s", path, required_bytes, available_bytes)
        if available_bytes < required_bytes:
            raise OSError(
                errno.ENOSPC,
                f"Archive staging requires {required_bytes} bytes on '{path}', but only {available_bytes} bytes are available.",
            )


def get_folder_size_mb(path) -> float:
    """Return the size of a folder in mebibytes.

    Args:
        path (str | Path): Folder whose contents should be measured.

    Returns:
        float: Total file size divided by 1024 squared.
    """
    return get_directory_size(path)


def has_disk_free_space(path_of_disk, mb_free):
    """Check whether a disk has strictly more than the requested free space.

    Args:
        path_of_disk (str | Path): Path on the disk to inspect.
        mb_free (float): Minimum free-space threshold in mebibytes.

    Returns:
        bool: Whether available free space is greater than the threshold.
    """
    stat = shutil.disk_usage(path_of_disk)
    spazio_disponibile_mb = stat.free / (1024 * 1024)
    if spazio_disponibile_mb > mb_free:
        return True
    else:
        return False


def get_free_space_mb(directory) -> float:
    """Return the available free space for a directory's filesystem.

    Args:
        directory (str | Path): Existing path on the filesystem to inspect.

    Returns:
        float: Available free space divided by 1024 squared.
    """
    return shutil.disk_usage(directory).free / (1024 * 1024)


def get_directory_size(path) -> float:
    """Return the total size of files under a directory in mebibytes.

    Args:
        path (str | Path): Directory whose contents should be measured.

    Returns:
        float: Total file size divided by 1024 squared.
    """
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            total_size += os.path.getsize(fp)
    return total_size / (1024 * 1024)


def check_move_dirs_free_space(src_path, dst_path) -> bool:
    """Check whether the destination has enough free space for a directory copy.

    Args:
        src_path (str | Path): Source directory whose current size is measured.
        dst_path (str | Path): Destination path whose filesystem capacity is checked.

    Returns:
        bool: Whether available destination space is at least the source size.
    """

    # Calculate the size of the source directory
    src_size_mb = get_directory_size(src_path)

    # Get the free space of the destination directory
    free_space_mb = get_free_space_mb(dst_path)

    # Check if there is enough space
    return free_space_mb >= src_size_mb
