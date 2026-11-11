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
    """Report equal-directory-weight progress, clamped to its valid range.

    A zero-byte directory counts as complete when the copy strategy emits its
    terminal callback. A stale byte estimate cannot make the reported value
    exceed 100 percent. Observer exceptions are allowed to propagate.
    """
    if not callback or directory_count <= 0:
        return
    directory_fraction = (copied_bytes / total_bytes) if total_bytes > 0 else 1.0
    directory_fraction = min(1.0, max(0.0, directory_fraction))
    overall_percentage = ((index + directory_fraction) / directory_count) * 100
    callback(int(min(100.0, max(0.0, overall_percentage))))
