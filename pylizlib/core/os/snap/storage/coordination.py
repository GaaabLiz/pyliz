"""Coordinate catalogue operations, observer reentry and abandoned-journal recovery."""

from __future__ import annotations

import inspect
import os
import threading
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
from operator import attrgetter
from pathlib import Path
from typing import Any
from weakref import WeakValueDictionary

from pylizlib.core.log.pylizLogger import logger
from pylizlib.core.os.filesystem.locking import FileLock, FileLockBusyError

CATALOGUE_LOCK_FILENAME = ".pyliz_snapshot.lock"
_in_observer = ContextVar("snapshot_observer", default=False)


class SnapshotBusyError(RuntimeError):
    """A competing operation or observer mutation cannot safely enter this catalogue."""


@dataclass
class _CatalogueLease:
    """Retain one catalogue's in-process owner while its stable native lock is held.

    Attributes:
        root (Path): Canonical catalogue path shared by cooperating callers.
        lock (threading.RLock): Nonblocking thread gate, reentrant only for the owning thread.
        depth (int): Number of nested internal calls holding this lease.
        owner (int | None): Owning thread identity, cleared on outermost context exit.
        active_journals (set[Path]): Workspaces created by this invocation and excluded from implicit recovery.
    """

    root: Path
    lock: Any = field(default_factory=threading.RLock)
    depth: int = 0
    owner: int | None = None
    active_journals: set[Path] = field(default_factory=set)


_leases: WeakValueDictionary[str, _CatalogueLease] = WeakValueDictionary()
_leases_gate = threading.Lock()


def _reset_coordination_after_fork() -> None:
    """Discard the parent's thread leases and observer state in a forked worker.

    Returns:
        None: The child must acquire a new native catalogue lock; a parent operation cannot be reentered.
    """
    global _leases, _leases_gate
    _leases = WeakValueDictionary()
    _leases_gate = threading.Lock()
    _in_observer.set(False)


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_reset_coordination_after_fork)


@contextmanager
def catalogue_access(path_catalogue: Path, *, write: bool = True) -> Iterator[None]:
    """Hold one catalogue gate across recovery, preflight, publication and cleanup.

    Internal calls on the owning thread reuse the gate. Metadata queries from
    callbacks are allowed; mutations from callbacks and competing threads or
    processes fail immediately, avoiding callback deadlocks and stale recovery.

    Args:
        path_catalogue (Path): Catalogue root; missing parents are created as for normal catalogue initialization.
        write (bool): True for mutations, export or backup; False only for metadata lookup and implicit recovery.

    Yields:
        None: Protected execution while the process and thread gates remain held.

    Raises:
        SnapshotBusyError: Another owner is active or an observer attempts a mutation.
        OSError: Native locking is unavailable; execution never continues without the lock.
        ValueError: The persistent sidecar is unsafe.
    """
    if write and _in_observer.get():
        raise SnapshotBusyError("Snapshot callback observers cannot start a modifying operation.")
    root = Path(path_catalogue).resolve(strict=False)
    key = os.path.normcase(str(root))
    with _leases_gate:
        lease = _leases.get(key)
        if lease is None:
            lease = _CatalogueLease(root)
            _leases[key] = lease
    if not lease.lock.acquire(blocking=False):
        raise SnapshotBusyError(f"Snapshot catalogue '{root}' is busy with another active operation.")
    try:
        if lease.depth:
            previous_journals = lease.active_journals.copy()
            lease.depth += 1
            try:
                yield
            finally:
                lease.active_journals.intersection_update(previous_journals)
                lease.depth -= 1
            return
        root.mkdir(parents=True, exist_ok=True)
        with ExitStack() as resources:
            try:
                resources.enter_context(FileLock(root / CATALOGUE_LOCK_FILENAME))
            except FileLockBusyError as error:
                raise SnapshotBusyError(f"Snapshot catalogue '{root}' is busy with another process.") from error
            lease.owner = threading.get_ident()
            lease.depth = 1
            logger.debug("Acquired snapshot catalogue gate at '%s'.", root)
            try:
                yield
            finally:
                lease.active_journals.clear()
                lease.depth = 0
                lease.owner = None
    finally:
        lease.lock.release()


def register_active_journal(workspace: Path) -> None:
    """Protect a local workspace from implicit recovery for the current operation's lifetime.

    Args:
        workspace (Path): Newly created or explicitly recovered workspace below a held catalogue scope.

    Returns:
        None: The most specific held catalogue lease retains the workspace until the creating operation returns.
            Standalone journal fixtures outside an operation remain recoverable immediately.
    """
    workspace = Path(workspace).resolve(strict=False)
    with _leases_gate:
        candidates = [lease for lease in list(_leases.values()) if lease.owner == threading.get_ident() and workspace.is_relative_to(lease.root)]
        if candidates:
            max(candidates, key=lambda lease: len(lease.root.parts)).active_journals.add(workspace)


def is_active_journal(workspace: Path) -> bool:
    """Identify a workspace owned by an operation on the current thread.

    Args:
        workspace (Path): Recovery candidate; foreign threads must acquire the catalogue gate before scanning.

    Returns:
        bool: True while a matching operation owns this exact workspace, including inside a metadata observer.
    """
    workspace = Path(workspace).resolve(strict=False)
    with _leases_gate:
        return any(lease.owner == threading.get_ident() and workspace in lease.active_journals for lease in list(_leases.values()))


def observer_callback(callback: Callable | None) -> Callable | None:
    """Mark external observer execution while preserving values and exceptions.

    Args:
        callback (Callable | None): Optional user progress or message callback.

    Returns:
        Callable | None: Equivalent callback running in a metadata-only observer context, or None.
    """
    if callback is None:
        return None

    @wraps(callback)
    def observe(*args, **kwargs):
        """Invoke the original callback and always restore the previous observer context.

        Args:
            args (tuple): Positional callback arguments retained unchanged.
            kwargs (dict): Keyword callback arguments retained unchanged.

        Returns:
            Any: Original callback return value; its exception propagates unchanged.
        """
        token = _in_observer.set(True)
        try:
            return callback(*args, **kwargs)
        finally:
            _in_observer.reset(token)

    return observe


def coordinated(scope_attribute: str) -> Callable:
    """Guard an internal operation entry point and its external observers.

    Public facades keep explicit context boundaries. Internal services also use
    this decorator so direct service calls receive the same safety guarantee.
    Only the named progress/message arguments are wrapped; copying providers,
    staging hooks and other internal collaborators keep their existing contract.

    Args:
        scope_attribute (str): Attribute path on the service yielding its catalogue root, such as
            ``storage.path_catalogue`` or ``path_catalogue``.

    Returns:
        Callable: Method decorator preserving the original signature and docstring through functools.wraps.
    """
    get_scope = attrgetter(scope_attribute)

    def decorate(method: Callable) -> Callable:
        """Bind one internal method signature and catalogue accessor.

        Args:
            method (Callable): Operation method accepting its service instance first.

        Returns:
            Callable: Guarded method with the same introspected public signature.
        """
        signature = inspect.signature(method)

        @wraps(method)
        def invoke(owner, *args, **kwargs):
            """Acquire the catalogue before invoking a service with guarded observers.

            Args:
                owner (object): Internal service holding the configured scope attribute.
                args (tuple): Operation positional arguments, bound using the original signature.
                kwargs (dict): Operation keyword arguments, bound using the original signature.

            Returns:
                Any: Original operation result; errors retain the existing operation policy.
            """
            with catalogue_access(get_scope(owner)):
                bound = signature.bind(owner, *args, **kwargs)
                for name in ("progress_callback", "message_callback"):
                    if name in bound.arguments:
                        bound.arguments[name] = observer_callback(bound.arguments[name])
                return method(*bound.args, **bound.kwargs)

        return invoke

    return decorate
