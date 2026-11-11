"""Observer contracts for copy bytes, snapshot percentages and search cancellation.

These are deliberately distinct: search callbacks can cancel the current
snapshot, whereas copy and percentage callbacks only report progress.
"""

from typing import Callable, Optional

CopyProgressCallback = Callable[[int, int], None]
SnapshotPercentCallback = Callable[[int], None]
MessageCallback = Callable[[str], None]
SnapshotProgressCallback = Callable[[str, int, int], Optional[bool]]


def report_directory_progress(callback: SnapshotPercentCallback | None, index: int, directory_count: int, copied_bytes: int, total_bytes: int) -> None:
    """Report the existing equal-directory-weight progress rounded down to int.

    Empty directories count as complete if the copy strategy notifies progress.
    This function does not invent notifications, suppress observer exceptions or
    alter when a strategy performs its preliminary total-byte scan.
    """
    if callback:
        directory_fraction = (copied_bytes / total_bytes) if total_bytes > 0 else 1.0
        overall_percentage = ((index + directory_fraction) / directory_count) * 100
        callback(int(overall_percentage))
