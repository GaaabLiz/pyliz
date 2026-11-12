"""Check cumulative byte requirements on each destination filesystem."""

import errno
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
        additional_requirements (Iterable[tuple[Path, int]]): Existing directories
            and additional bytes retained simultaneously, including final copies.

    Returns:
        None: If each device currently has at least its cumulative requirement.

    Raises:
        FileNotFoundError: If a required directory is absent or is not a directory.
        OSError: If stat/disk usage fails, or ENOSPC when a device lacks space.

    Notes:
        Space is observed, not reserved against concurrent writers. Byte counts
        are supplied by the caller and are not rounded to allocation units.
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
