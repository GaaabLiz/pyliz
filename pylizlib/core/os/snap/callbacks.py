"""Observer contracts for copy bytes, snapshot percentages and search cancellation.

These are deliberately distinct: search callbacks can cancel the current
snapshot, whereas copy and percentage callbacks only report progress.

Attributes:
    CopyProgressCallback (Callable[[int, int], None]): Observer receiving copied and
        estimated total bytes for one directory. Totals are clamped to actual copied
        bytes and a terminal notification also covers an empty tree. Return values
        do not cancel copying; observer errors propagate through the operation policy.
    SnapshotPercentCallback (Callable[[int], None]): Observer receiving a clamped
        integer percentage from 0 to 100. Each association has equal weight regardless
        of byte size; return values are informational rather than cancellable.
    MessageCallback (Callable[[str], None]): Observer receiving one status message.
        Existing localized messages are retained and exceptions are not silently ignored.
    SnapshotProgressCallback (Callable[[str, int, int], bool | None]): Search observer
        receiving filename, capped candidate-file count and one-based processed-file
        index. Content scans repeat notifications during chunks. Only literal False
        cancels the current snapshot; None and 0 do not. search_list can continue with
        later snapshots and observer exceptions propagate unchanged.
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

    Args:
        callback (SnapshotPercentCallback | None): Optional percentage observer receiving one integer from 0
            through 100; exceptions propagate.
        index (int): Zero-based directory position used for equal-directory-weight progress.
        directory_count (int): Number of equally weighted directories used to compute aggregate percentage
            progress.
        copied_bytes (int): Bytes copied so far for the current directory, before clamping aggregate progress.
        total_bytes (int): Estimated total bytes for progress; completed notifications use actual copied bytes,
            including zero-byte trees.

    Returns:
        None: No return value.
    """
    if not callback or directory_count <= 0:
        return
    directory_fraction = (copied_bytes / total_bytes) if total_bytes > 0 else 1.0
    directory_fraction = min(1.0, max(0.0, directory_fraction))
    overall_percentage = ((index + directory_fraction) / directory_count) * 100
    callback(int(min(100.0, max(0.0, overall_percentage))))
