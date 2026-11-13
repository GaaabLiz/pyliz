"""Native sidecar locks coordinate processes without replacing their shared inode."""

import multiprocessing
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from pylizlib.core.os.filesystem.locking import FileLock, FileLockBusyError


def _child(lock: Path, *, crash: bool = False) -> subprocess.CompletedProcess:
    """Try the native primitive in a fresh interpreter with a bounded process lifetime."""
    code = "\n".join(
        [
            "import os, sys",
            "from pathlib import Path",
            "from pylizlib.core.os.filesystem.locking import FileLock, FileLockBusyError",
            "try:",
            "    with FileLock(Path(sys.argv[1])):",
            "        if sys.argv[2] == 'crash': os._exit(0)",
            "except FileLockBusyError:",
            "    sys.exit(23)",
        ]
    )
    return subprocess.run([sys.executable, "-c", code, str(lock), "crash" if crash else "normal"], capture_output=True, text=True, timeout=15)


def test_competing_process_is_rejected_then_can_reuse_the_same_sidecar(tmp_path):
    """The OS releases ownership on close without truncating or unlinking the lock file."""
    path = tmp_path / "coordination.lock"
    path.write_bytes(b"existing sidecar")
    identity = path.stat().st_ino
    with FileLock(path):
        child = _child(path)
        assert child.returncode == 23, child.stderr
    # Windows denies reads that overlap the byte range held by msvcrt.locking.
    assert path.read_bytes() == b"existing sidecar"
    assert path.stat().st_ino == identity
    child = _child(path)
    assert child.returncode == 0, child.stderr
    assert path.read_bytes() == b"existing sidecar"


def test_separate_lock_objects_do_not_share_ownership(tmp_path):
    """Two independent acquisitions must contend even within the same process."""
    path = tmp_path / "coordination.lock"
    with FileLock(path):
        with pytest.raises(FileLockBusyError):
            with FileLock(path):
                pytest.fail("a second independent lock was acquired")


def test_native_lock_is_released_after_abrupt_process_exit(tmp_path):
    """A terminated writer does not leave a stale ownership marker blocking recovery."""
    path = tmp_path / "coordination.lock"
    child = _child(path, crash=True)
    assert child.returncode == 0, child.stderr
    with FileLock(path):
        assert path.is_file()


@pytest.mark.parametrize("termination", [RuntimeError, SystemExit])
def test_exceptional_exit_releases_the_descriptor(tmp_path, termination):
    """Both ordinary errors and crash simulations release ownership while preserving the sidecar."""
    path = tmp_path / "coordination.lock"
    with pytest.raises(termination):
        with FileLock(path):
            raise termination("interrupted")
    with FileLock(path):
        assert path.exists()


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "directory"])
def test_unsafe_sidecars_never_modify_another_entry(tmp_path, kind):
    """Coordination must not follow a linked path or treat user data as a lock directory."""
    original = tmp_path / "important"
    original.write_bytes(b"preserve")
    path = tmp_path / "coordination.lock"
    try:
        if kind == "symlink":
            path.symlink_to(original)
        elif kind == "hardlink":
            os.link(original, path)
        else:
            path.mkdir()
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"{kind} fixture is unavailable: {error}")
    with pytest.raises((ValueError, OSError)):
        with FileLock(path):
            pytest.fail("an unsafe lock path was accepted")
    assert original.read_bytes() == b"preserve"


def test_backend_failure_closes_the_descriptor_and_does_not_continue_unlocked(tmp_path):
    """A native locking failure must propagate, and a later valid acquisition can succeed."""
    path = tmp_path / "coordination.lock"
    with patch.object(FileLock, "_acquire", side_effect=OSError("native locking unavailable")):
        with pytest.raises(OSError, match="unavailable"):
            with FileLock(path):
                pytest.fail("execution continued without coordination")
    with FileLock(path):
        assert path.exists()


def _fork_lock_probe(path: Path, inherited: FileLock, connection) -> None:
    """Check contention during parent ownership and acquire again after the parent releases."""
    try:
        assert inherited._descriptor is None
        try:
            with FileLock(path):
                connection.send("incorrect ownership")
                return
        except FileLockBusyError:
            connection.send("busy")
        assert connection.recv() == "retry"
        with FileLock(path):
            connection.send("acquired")
    finally:
        connection.close()


@pytest.mark.skipif(not hasattr(os, "fork"), reason="native fork is unavailable")
def test_forked_children_do_not_retain_the_parent_lock_descriptor(tmp_path):
    """An idle child cannot keep a released parent's lock alive through an inherited open file description."""
    context = multiprocessing.get_context("fork")
    parent, child = context.Pipe()
    path = tmp_path / "coordination.lock"
    with FileLock(path) as inherited:
        process = context.Process(target=_fork_lock_probe, args=(path, inherited, child))
        process.start()
        child.close()
        try:
            assert parent.poll(10), "forked lock probe did not start"
            assert parent.recv() == "busy"
        except BaseException:
            process.terminate()
            process.join(timeout=10)
            parent.close()
            raise
    try:
        parent.send("retry")
        assert parent.poll(10), "forked lock probe could not retry"
        assert parent.recv() == "acquired"
        process.join(timeout=10)
        assert process.exitcode == 0
    finally:
        if process.is_alive():
            process.terminate()
            process.join(timeout=10)
        parent.close()
