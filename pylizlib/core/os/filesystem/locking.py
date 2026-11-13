"""Nonblocking process locks using a stable, caller-owned filesystem sidecar."""

from __future__ import annotations

import os
import stat
import threading
from pathlib import Path
from types import TracebackType
from weakref import WeakSet

from pylizlib.core.os.filesystem.tree import is_link_or_junction

_active_locks: WeakSet[FileLock] = WeakSet()
_active_gate = threading.Lock()


class FileLockBusyError(RuntimeError):
    """Another cooperating process already owns the requested advisory lock."""


class FileLock:
    """Hold an exclusive advisory lock until context exit, including exceptional exits.

    The parent directory must exist. The sidecar remains after release: unlinking
    it would let another process lock a different inode at the same pathname.
    Only cooperating users of the same sidecar are coordinated. Network shares
    depend on the server's native advisory-lock support. Forked children close
    inherited lock descriptors and must acquire ownership independently.

    Attributes:
        path (Path): Stable sidecar path, opened without truncating its existing contents.
    """

    def __init__(self, path: Path):
        """Bind a lock sidecar without opening or modifying it.

        Args:
            path (Path): File used exclusively for coordination; links and non-regular files are rejected.

        Returns:
            None: Acquisition occurs on context entry.
        """
        self.path = Path(path)
        self._descriptor: int | None = None

    def __enter__(self) -> FileLock:
        """Acquire the native lock immediately or fail before returning control.

        Returns:
            FileLock: This acquired context, retaining its open descriptor until exit.

        Raises:
            FileLockBusyError: Another process owns the sidecar lock.
            ValueError: The sidecar is linked, non-regular or changes identity during acquisition.
            OSError: Opening or locking fails for another reason; callers must not proceed unlocked.
        """
        with _active_gate:
            if self._descriptor is not None:
                raise RuntimeError("A FileLock instance cannot be entered twice.")
            if is_link_or_junction(self.path):
                raise ValueError(f"Lock sidecar '{self.path}' cannot be a link.")
            descriptor = os.open(self.path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
            try:
                opened = os.fstat(descriptor)
                if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
                    raise ValueError(f"Lock sidecar '{self.path}' must be a private regular file.")
                self._acquire(descriptor)
                current = self.path.lstat()
                if is_link_or_junction(self.path) or (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
                    raise ValueError(f"Lock sidecar '{self.path}' changed during acquisition.")
            except BaseException:
                os.close(descriptor)
                raise
            self._descriptor = descriptor
            _active_locks.add(self)
        return self

    def __exit__(self, exception_type: type[BaseException] | None, exception: BaseException | None, traceback: TracebackType | None) -> None:
        """Close the descriptor and release its lock while propagating any caller exception.

        Args:
            exception_type (type[BaseException] | None): Exception class from the protected block, if any.
            exception (BaseException | None): Exception instance from the protected block, if any.
            traceback (TracebackType | None): Associated caller traceback, if any.

        Returns:
            None: Exceptions are never suppressed and the sidecar is never unlinked.
        """
        with _active_gate:
            descriptor, self._descriptor = self._descriptor, None
            _active_locks.discard(self)
            if descriptor is not None:
                os.close(descriptor)

    @staticmethod
    def _acquire(descriptor: int) -> None:
        """Acquire a native exclusive nonblocking lock without importing foreign-platform bindings.

        Args:
            descriptor (int): Open regular file descriptor positioned at byte zero.

        Returns:
            None: The descriptor owns the lock until it closes.

        Raises:
            FileLockBusyError: A native contention error reports another owner.
            OSError: The native backend fails for another reason.
        """
        if os.name == "nt":
            import errno
            import msvcrt

            try:
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            except OSError as error:
                if error.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                    raise FileLockBusyError("File lock is already in use.") from error
                raise
        else:
            import fcntl

            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise FileLockBusyError("File lock is already in use.") from error


def _release_inherited_locks() -> None:
    """Close fork-inherited descriptors without unlocking their parent's open file descriptions.

    Returns:
        None: The child owns no inherited lock context and can acquire independent sidecars. The fork gate,
            acquired before the fork, is released for the child's future acquisitions.
    """
    for lock in list(_active_locks):
        descriptor, lock._descriptor = lock._descriptor, None
        if descriptor is not None:
            os.close(descriptor)
    _active_locks.clear()
    _active_gate.release()


if hasattr(os, "register_at_fork"):
    os.register_at_fork(before=_active_gate.acquire, after_in_parent=_active_gate.release, after_in_child=_release_inherited_locks)
