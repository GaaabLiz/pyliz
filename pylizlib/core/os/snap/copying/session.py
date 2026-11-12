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
    """

    def __init__(
        self, destination: Path, capture_integrity: bool, observed: IntegrityManifest | None, total_bytes: int, progress_callback: ProgressCallback | None, message_callback: MessageCallback | None
    ):
        """Capture the already-computed totals without performing additional I/O."""
        self.destination = destination
        self.capture_integrity = capture_integrity
        self.observed = observed
        self.total_bytes = total_bytes
        self.copied_bytes = 0
        self.progress_callback = progress_callback
        self.message_callback = message_callback
        self.last_progress: tuple[int, int] | None = None

    def copy_file(self, src: str, dst: str, *, follow_symlinks: bool = True) -> str:
        """Copy and optionally hash exactly the bytes written, then report progress."""
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
        """Report the exact completed total, including when no files were copied."""
        if self.progress_callback and self.last_progress != (self.copied_bytes, self.copied_bytes):
            self.progress_callback(self.copied_bytes, self.copied_bytes)
            self.last_progress = (self.copied_bytes, self.copied_bytes)

    def record_directories(self) -> None:
        """Record stored directories, including empty ones, after file copying."""
        assert self.observed is not None

        def raise_walk_error(error: OSError) -> None:
            """Propagate a walk failure instead of treating an incomplete scan as success."""
            raise error

        for current, directories, _ in os.walk(self.destination, onerror=raise_walk_error):
            directories[:] = sorted(directories)
            for name in directories:
                relative_path = (Path(current) / name).relative_to(self.destination).as_posix()
                self.observed[relative_path] = {"type": "directory", "size": 0, "sha256": None}
