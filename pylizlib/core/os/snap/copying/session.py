"""Per-call copy counters and captured integrity records."""

import hashlib
import os
import shutil
from pathlib import Path

from pylizlib.core.os.snap.callbacks import CopyProgressCallback as ProgressCallback
from pylizlib.core.os.snap.callbacks import MessageCallback
from pylizlib.core.os.snap.integrity import IntegrityManifest


class _FileCopySession:
    """Per-call byte counters and manifest recording for sequential file copying.

    A strategy remains reusable: this mutable state belongs to one destination,
    not to the strategy instance or a process-wide default settings object.

    Attributes:
        destination (Path): Target path receiving the copied content or metadata.
        capture_integrity (bool): Whether to hash and record the exact bytes written into this attempt's integrity
            mapping.
        observed (IntegrityManifest | None): Observed integrity mapping or entry identity to compare with the
            expected value.
        total_bytes (int): Estimated total bytes for progress; completed notifications use actual copied bytes,
            including zero-byte trees.
        copied_bytes (int): Actual bytes reported copied by this file-copy session.
        progress_callback (ProgressCallback | None): Optional progress observer; notification units are defined by
            this operation.
        message_callback (MessageCallback | None): Optional status observer receiving one message string; its
            exceptions propagate according to the calling operation.
        last_progress (tuple[int, int] | None): Last emitted (copied, total) byte pair, used to avoid a duplicate
            terminal notification.
    """

    def __init__(
        self, destination: Path, capture_integrity: bool, observed: IntegrityManifest | None, total_bytes: int, progress_callback: ProgressCallback | None, message_callback: MessageCallback | None
    ):
        """Capture the already-computed totals without performing additional I/O.

        Args:
            destination (Path): Target path receiving the copied content or metadata.
            capture_integrity (bool): Whether to hash and record the exact bytes written into this attempt's integrity
                mapping.
            observed (IntegrityManifest | None): Observed integrity mapping or entry identity to compare with the
                expected value.
            total_bytes (int): Estimated total bytes for progress; completed notifications use actual copied bytes,
                including zero-byte trees.
            progress_callback (ProgressCallback | None): Optional observer receiving (copied_bytes, total_bytes),
                including terminal empty-tree progress; return values do not cancel copying.
            message_callback (MessageCallback | None): Optional status observer receiving one message string; its
                exceptions propagate according to the calling operation.

        Returns:
            None: No return value.
        """
        self.destination = destination
        self.capture_integrity = capture_integrity
        self.observed = observed
        self.total_bytes = total_bytes
        self.copied_bytes = 0
        self.progress_callback = progress_callback
        self.message_callback = message_callback
        self.last_progress: tuple[int, int] | None = None

    def copy_file(self, src: str, dst: str, *, follow_symlinks: bool = True) -> str:
        """Copy and optionally hash exactly the bytes written, then report progress.

        Args:
            src (str): Native source filename supplied by shutil's copy callback.
            dst (str): Native destination filename supplied by shutil's copy callback.
            follow_symlinks (bool): Forwarded standard metadata/copy behavior; outer snapshot copy policy
                independently rejects tree links.

        Returns:
            str: Destination filename returned by the standard copy callback contract, after any hash/progress update.
        """
        if self.message_callback:
            self.message_callback(f"Copia in corso: {Path(src).name}")
        if self.capture_integrity:
            digest = hashlib.sha256()
            file_size = 0
            with open(src, "rb") as source_file, open(dst, "xb") as destination_file:
                for chunk in iter(lambda: source_file.read(1024 * 1024), b""):
                    destination_file.write(chunk)
                    digest.update(chunk)
                    file_size += len(chunk)
            shutil.copystat(src, dst, follow_symlinks=follow_symlinks)
            relative_path = Path(dst).relative_to(self.destination).as_posix()
            assert self.observed is not None
            self.observed[relative_path] = {"type": "file", "size": file_size, "sha256": digest.hexdigest()}
            result = dst
        else:
            result = shutil.copy2(src, dst, follow_symlinks=follow_symlinks)
        if self.progress_callback:
            self.copied_bytes += Path(dst).stat().st_size
            total_bytes = max(self.total_bytes, self.copied_bytes)
            self.progress_callback(self.copied_bytes, total_bytes)
            self.last_progress = (self.copied_bytes, total_bytes)
        return result

    def finish(self) -> None:
        """Report the exact completed total, including when no files were copied.

        Returns:
            None: No return value.
        """
        if self.progress_callback and self.last_progress != (self.copied_bytes, self.copied_bytes):
            self.progress_callback(self.copied_bytes, self.copied_bytes)
            self.last_progress = (self.copied_bytes, self.copied_bytes)

    def record_directories(self) -> None:
        """Record stored directories, including empty ones, after file copying.

        Returns:
            None: No return value.
        """
        assert self.observed is not None

        def raise_walk_error(error: OSError) -> None:
            """Propagate a walk failure instead of treating an incomplete scan as success.

            Args:
                error (OSError): Original failure to propagate or preserve as the cause of a rollback failure.

            Returns:
                None: No return value.
            """
            raise error

        for current, directories, _ in os.walk(self.destination, onerror=raise_walk_error):
            directories[:] = sorted(directories)
            for name in directories:
                relative_path = (Path(current) / name).relative_to(self.destination).as_posix()
                self.observed[relative_path] = {"type": "directory", "size": 0, "sha256": None}
