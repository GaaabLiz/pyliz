"""Pluggable strategies for copying snapshot directory trees."""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
import tempfile
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import ContextManager

ProgressCallback = Callable[[int, int], None]
MessageCallback = Callable[[str], None]


class SourceChangedError(RuntimeError):
    """Raised when the source tree changes during each verified copy attempt."""


class DirectoryCopyStrategy(ABC):
    """Common contract for copying a source directory into a new destination.

    Implementations must create ``destination`` on success and remove their
    partial destination if copying fails. The destination must not exist when
    the method starts.
    """

    @abstractmethod
    def copy_directory(
        self,
        source: Path,
        destination: Path,
        progress_callback: ProgressCallback | None = None,
        message_callback: MessageCallback | None = None,
    ) -> Path:
        """Copy a directory tree and return its published destination."""


def _remove_tree(path: Path) -> None:
    """Remove only the named entry, never follow a symlink at its root."""
    if path.is_symlink():
        path.unlink(missing_ok=True)
    elif path.exists():
        shutil.rmtree(path)


def _is_link_or_junction(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return is_junction is not None and is_junction()


class SequentialFileCopyStrategy(DirectoryCopyStrategy):
    """Copy files in sequence, preserving the library's current default."""

    @staticmethod
    def _total_bytes(source: Path) -> int:
        def raise_walk_error(error: OSError) -> None:
            raise error

        total = 0
        for current, directories, files in os.walk(source, onerror=raise_walk_error):
            # os.walk does not descend into symlink directories unless asked.
            directories[:] = [name for name in directories if not (Path(current) / name).is_symlink()]
            for name in files:
                total += (Path(current) / name).stat().st_size
        return total

    def copy_directory(
        self,
        source: Path,
        destination: Path,
        progress_callback: ProgressCallback | None = None,
        message_callback: MessageCallback | None = None,
    ) -> Path:
        source = Path(source)
        destination = Path(destination)
        if not source.is_dir():
            raise NotADirectoryError(f"Copy source '{source}' is not a directory.")
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(f"Copy destination '{destination}' already exists.")
        destination.parent.mkdir(parents=True, exist_ok=True)

        total_bytes = self._total_bytes(source) if progress_callback else 0
        copied_bytes = 0

        def copy_file(src: str, dst: str, *, follow_symlinks: bool = True) -> str:
            nonlocal copied_bytes
            if message_callback:
                message_callback(f"Copia in corso: {Path(src).name}")
            result = shutil.copy2(src, dst, follow_symlinks=follow_symlinks)
            if progress_callback:
                copied_bytes += Path(dst).stat().st_size
                progress_callback(copied_bytes, total_bytes)
            return result

        try:
            destination.mkdir()
            for source_item in source.iterdir():
                destination_item = destination / source_item.name
                if source_item.is_dir():
                    shutil.copytree(source_item, destination_item, copy_function=copy_file)
                else:
                    copy_file(str(source_item), str(destination_item))
        except Exception:
            _remove_tree(destination)
            raise
        return destination


class VerifiedFileCopyStrategy(DirectoryCopyStrategy):
    """Retry a sequential copy when a content-hash manifest changes.

    This detects changes visible between the pre-copy and post-copy scans and
    refuses to publish after repeated changes. It is not a filesystem snapshot:
    an ABA change or a writer coordinated with the scans can evade detection.
    Use ``ProviderSnapshotCopyStrategy`` for a source frozen by the filesystem,
    server, or application.
    """

    def __init__(self, max_attempts: int = 3, delegate: DirectoryCopyStrategy | None = None):
        if type(max_attempts) is not int or max_attempts < 1:
            raise ValueError("max_attempts must be a positive integer.")
        self.max_attempts = max_attempts
        self.delegate = delegate or SequentialFileCopyStrategy()

    @staticmethod
    def _manifest(root: Path) -> dict[str, tuple[str, int | str]]:
        root_mode = root.lstat().st_mode
        if _is_link_or_junction(root) or not stat.S_ISDIR(root_mode):
            raise NotADirectoryError(f"Copy source '{root}' is not a real directory.")

        manifest: dict[str, tuple[str, int | str]] = {".": ("directory", 0)}
        pending = [root]
        while pending:
            current = pending.pop()
            with os.scandir(current) as entries:
                for entry in entries:
                    relative = Path(entry.path).relative_to(root).as_posix()
                    entry_path = Path(entry.path)
                    mode = entry.stat(follow_symlinks=False).st_mode
                    if stat.S_ISLNK(mode) or _is_link_or_junction(entry_path):
                        raise ValueError(f"Verified copy does not accept symbolic links: '{entry.path}'.")
                    if stat.S_ISDIR(mode):
                        manifest[relative] = ("directory", 0)
                        pending.append(Path(entry.path))
                    elif stat.S_ISREG(mode):
                        digest = hashlib.sha256()
                        with Path(entry.path).open("rb") as file:
                            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                                digest.update(chunk)
                        manifest[relative] = (digest.hexdigest(), entry.stat(follow_symlinks=False).st_size)
                    else:
                        raise ValueError(f"Verified copy does not accept special file '{entry.path}'.")
        return manifest

    def copy_directory(
        self,
        source: Path,
        destination: Path,
        progress_callback: ProgressCallback | None = None,
        message_callback: MessageCallback | None = None,
    ) -> Path:
        source = Path(source)
        destination = Path(destination)
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(f"Copy destination '{destination}' already exists.")
        destination.parent.mkdir(parents=True, exist_ok=True)

        for attempt in range(1, self.max_attempts + 1):
            before = self._manifest(source)
            with tempfile.TemporaryDirectory(prefix=".verified_copy_", dir=destination.parent) as temporary_directory:
                staged = Path(temporary_directory) / "copy"
                self.delegate.copy_directory(source, staged, progress_callback, message_callback)
                after = self._manifest(source)
                if before == after:
                    if destination.exists() or destination.is_symlink():
                        raise FileExistsError(f"Copy destination '{destination}' was created during copying.")
                    staged.rename(destination)
                    return destination
            if attempt < self.max_attempts and message_callback:
                message_callback(f"Sorgente modificata durante la copia; nuovo tentativo {attempt + 1}/{self.max_attempts}.")

        raise SourceChangedError(f"Source '{source}' changed during all {self.max_attempts} copy attempts.")


class SourceSnapshotProvider(ABC):
    """Adapter for a filesystem, server, or application snapshot facility."""

    @abstractmethod
    def create_snapshot(self, source: Path) -> ContextManager[Path]:
        """Yield a stable point-in-time directory for ``source``."""


class ProviderSnapshotCopyStrategy(DirectoryCopyStrategy):
    """Copy from a stable tree supplied by a snapshot provider.

    The provider must either hold all writers quiesced for the context or yield
    an immutable filesystem/server snapshot. The strategy cannot enforce the
    provider's consistency guarantee itself.
    """

    def __init__(self, provider: SourceSnapshotProvider, delegate: DirectoryCopyStrategy | None = None):
        if not isinstance(provider, SourceSnapshotProvider):
            raise TypeError("provider must implement SourceSnapshotProvider.")
        self.provider = provider
        self.delegate = delegate or SequentialFileCopyStrategy()

    def copy_directory(
        self,
        source: Path,
        destination: Path,
        progress_callback: ProgressCallback | None = None,
        message_callback: MessageCallback | None = None,
    ) -> Path:
        destination = Path(destination)
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(f"Copy destination '{destination}' already exists.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".provider_copy_", dir=destination.parent) as temporary_directory:
            staged = Path(temporary_directory) / "copy"
            self._copy_from_provider(source, staged, progress_callback, message_callback)
            if destination.exists() or destination.is_symlink():
                raise FileExistsError(f"Copy destination '{destination}' was created during copying.")
            staged.rename(destination)
        return destination

    def _copy_from_provider(
        self,
        source: Path,
        destination: Path,
        progress_callback: ProgressCallback | None,
        message_callback: MessageCallback | None,
    ) -> Path:
        with self.provider.create_snapshot(Path(source)) as stable_source:
            stable_source = Path(stable_source)
            if _is_link_or_junction(stable_source) or not stable_source.is_dir():
                raise NotADirectoryError(f"Snapshot provider returned invalid source '{stable_source}'.")
            return self.delegate.copy_directory(stable_source, destination, progress_callback, message_callback)
