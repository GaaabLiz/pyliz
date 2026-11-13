"""Active operations must never be mistaken for abandoned recovery work."""

import multiprocessing
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import pytest

from pylizlib.core.os.snap import BackupType, SnapDirAssociation, Snapshot, SnapshotBusyError, SnapshotCatalogue, SnapshotManager, SnapshotSettings


def _snapshot(root: Path, identity: str) -> Snapshot:
    """Build a deterministic public model with a distinct isolated source tree."""
    source = root / identity
    source.mkdir()
    (source / "identity").write_bytes(identity.encode())
    return Snapshot(identity, identity, "", directories=[SnapDirAssociation(0, str(source), f"folder-{identity}")])


@pytest.mark.parametrize("callback_kind", ["progress", "message"])
def test_catalogue_queries_inside_create_callbacks_preserve_active_staging(snapshot_workspace: Path, callback_kind: str) -> None:
    """Status observers can inspect published snapshots without rolling back the current creation."""
    catalogue = SnapshotCatalogue(snapshot_workspace / "catalogue", SnapshotSettings())
    previous = _snapshot(snapshot_workspace, "previous")
    catalogue.add(previous)
    current = _snapshot(snapshot_workspace, "current")
    observed = []

    def inspect(*_args):
        """Exercise every recovery-aware metadata query from inside the live copy."""
        snapshots = catalogue.get_all(strict=True)
        assert previous.id in {snapshot.id for snapshot in snapshots}
        assert catalogue.get_by_id(previous.id).id == previous.id
        assert catalogue.exists(previous.id)
        observed.append(True)

    catalogue.add(current, **{f"{callback_kind}_callback": inspect})
    assert observed
    for snapshot in [previous, current]:
        assert (catalogue.path_catalogue / snapshot.id / snapshot.directories[0].directory_name / "identity").read_bytes() == snapshot.id.encode()
    assert not list(catalogue.path_catalogue.rglob("journal.json"))


def test_another_thread_cannot_recover_an_active_creation(snapshot_workspace: Path) -> None:
    """A competing reader fails before it can remove an active writer's staging."""
    catalogue = SnapshotCatalogue(snapshot_workspace / "catalogue", SnapshotSettings())
    snapshot = _snapshot(snapshot_workspace, "threaded")
    observed = []

    def inspect(_percentage):
        """Keep the writer paused while a competing metadata read runs on another thread."""
        if observed:
            return
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(catalogue.get_all)
            with pytest.raises(RuntimeError, match="[Bb]usy|active|in use"):
                future.result(timeout=10)
        observed.append(True)

    catalogue.add(snapshot, progress_callback=inspect)
    assert observed
    assert catalogue.get_by_id(snapshot.id) is not None
    assert not list(catalogue.path_catalogue.rglob("journal.json"))


def test_callback_write_is_rejected_before_deleting_an_existing_snapshot(snapshot_workspace: Path) -> None:
    """Reentrant mutations are rejected while metadata reads from observers remain possible."""
    catalogue = SnapshotCatalogue(snapshot_workspace / "catalogue", SnapshotSettings())
    previous = _snapshot(snapshot_workspace, "previous")
    catalogue.add(previous)
    observed = []

    def mutate(_percentage):
        """Attempt a destructive operation while another snapshot is being created."""
        if observed:
            return
        with pytest.raises(RuntimeError, match="[Bb]usy|observer|callback"):
            catalogue.delete(previous)
        observed.append(True)

    catalogue.add(_snapshot(snapshot_workspace, "current"), progress_callback=mutate)
    assert observed
    assert (catalogue.path_catalogue / previous.id / previous.directories[0].directory_name / "identity").read_bytes() == b"previous"


@pytest.mark.parametrize("entrypoint", ["catalogue-read", "snapshot-read", "direct-recovery", "manager-write"])
def test_another_process_cannot_recover_or_modify_an_active_operation(snapshot_workspace: Path, entrypoint: str) -> None:
    """The stable OS lock protects every public facade and direct implicit-recovery entry point."""
    catalogue = SnapshotCatalogue(snapshot_workspace / "catalogue", SnapshotSettings())
    previous = _snapshot(snapshot_workspace, "previous")
    catalogue.add(previous)
    code = "\n".join(
        [
            "import sys",
            "from pathlib import Path",
            "from pylizlib.core.os.snap import Snapshot, SnapshotCatalogue, SnapshotManager, SnapshotBusyError",
            "from pylizlib.core.os.snap.storage.transactions import recover_pending_transactions",
            "root = Path(sys.argv[1])",
            "catalogue = SnapshotCatalogue(root)",
            "try:",
            "    if sys.argv[2] == 'catalogue-read': catalogue.get_all()",
            "    elif sys.argv[2] == 'snapshot-read': catalogue.get_by_id('previous')",
            "    elif sys.argv[2] == 'direct-recovery': recover_pending_transactions(root)",
            "    else: SnapshotManager(Snapshot('previous', 'previous', ''), root).delete()",
            "except SnapshotBusyError:",
            "    sys.exit(0)",
            "sys.exit(31)",
        ]
    )
    observed = []

    def inspect(_percentage):
        """Keep an actual creation in progress until the competing child has finished."""
        if observed:
            return
        result = subprocess.run([sys.executable, "-c", code, str(catalogue.path_catalogue), entrypoint], capture_output=True, text=True, timeout=15)
        assert result.returncode == 0, result.stderr
        observed.append(True)

    catalogue.add(_snapshot(snapshot_workspace, "current"), progress_callback=inspect)
    assert observed
    assert {snapshot.id for snapshot in catalogue.get_all()} == {"previous", "current"}
    assert (catalogue.path_catalogue / previous.id / previous.directories[0].directory_name / "identity").read_bytes() == b"previous"


@pytest.mark.parametrize("operation", ["install-replace", "install-merge", "sync", "edit-add", "backup", "duplicate"])
def test_metadata_queries_from_other_operation_observers_do_not_trigger_recovery(snapshot_workspace: Path, operation: str) -> None:
    """Callbacks across transaction types can read metadata without consuming in-flight workspaces."""
    catalogue = SnapshotCatalogue(snapshot_workspace / "catalogue", SnapshotSettings())
    snapshot = _snapshot(snapshot_workspace, "stored")
    catalogue.add(snapshot)
    manager = SnapshotManager(snapshot, catalogue.path_catalogue, catalogue.settings)
    observed = []

    def inspect(*_args):
        """Read through a fresh facade sharing the canonical catalogue scope."""
        other = SnapshotCatalogue(catalogue.path_catalogue, catalogue.settings)
        assert other.get_by_id(snapshot.id) is not None
        assert other.get_all(strict=True)
        with pytest.raises(SnapshotBusyError):
            other.delete(snapshot)
        observed.append(True)

    if operation.startswith("install"):
        (Path(snapshot.directories[0].original_path) / "identity").write_bytes(b"live changes")
        catalogue.install(snapshot, clear_destination=operation == "install-replace", progress_callback=inspect, message_callback=inspect)
        assert (Path(snapshot.directories[0].original_path) / "identity").read_bytes() == b"stored"
    elif operation == "sync":
        (Path(snapshot.directories[0].original_path) / "identity").write_bytes(b"new captured contents")
        manager.update_associated_dirs_from_system(message_callback=inspect)
        assert (manager.path_snapshot / snapshot.directories[0].directory_name / "identity").read_bytes() == b"new captured contents"
    elif operation == "edit-add":
        updated = snapshot.clone()
        addition = _snapshot(snapshot_workspace, "added").directories[0]
        addition.index = 1
        updated.directories.append(addition)
        catalogue.update_snapshot_by_objs(snapshot, updated, message_callback=inspect)
        assert (manager.path_snapshot / addition.directory_name / "identity").read_bytes() == b"added"
    elif operation == "backup":
        archive = manager.create_backup(snapshot_workspace / "exports", "observer", BackupType.SNAPSHOT_DIRECTORY, message_callback=inspect)
        assert archive.is_file()
    else:
        manager.duplicate(message_callback=inspect)
        assert len(catalogue.get_all()) == 2
    assert observed
    assert not list(catalogue.path_catalogue.rglob("journal.json"))


def test_real_process_termination_releases_gate_for_recovery(snapshot_workspace: Path) -> None:
    """A fresh reader can roll back a journal left by a writer terminated during copying."""
    catalogue_path = snapshot_workspace / "catalogue"
    snapshot = _snapshot(snapshot_workspace, "terminated")
    code = "\n".join(
        [
            "import os, sys",
            "from pathlib import Path",
            "from pylizlib.core.os.snap import SnapDirAssociation, Snapshot, SnapshotCatalogue",
            "root = Path(sys.argv[1])",
            "snapshot = Snapshot('terminated', 'terminated', '', directories=[SnapDirAssociation(0, str(root / 'terminated'), 'folder-terminated')])",
            "SnapshotCatalogue(root / 'catalogue').add(snapshot, progress_callback=lambda percentage: os._exit(47))",
        ]
    )
    result = subprocess.run([sys.executable, "-c", code, str(snapshot_workspace)], capture_output=True, text=True, timeout=15)
    assert result.returncode == 47, result.stderr
    assert list(catalogue_path.rglob("journal.json"))
    catalogue = SnapshotCatalogue(catalogue_path, SnapshotSettings())
    assert catalogue.get_all() == []
    assert not list(catalogue_path.rglob("journal.json"))
    catalogue.add(snapshot)
    assert catalogue.get_by_id(snapshot.id) is not None


def test_storage_locking_failure_does_not_touch_published_snapshot(snapshot_workspace: Path) -> None:
    """Unsupported or denied native locks stop a destructive public call before any filesystem mutation."""
    from pylizlib.core.os.filesystem.locking import FileLock

    catalogue = SnapshotCatalogue(snapshot_workspace / "catalogue", SnapshotSettings())
    snapshot = _snapshot(snapshot_workspace, "preserved")
    catalogue.add(snapshot)
    with patch.object(FileLock, "_acquire", side_effect=OSError("native locking unavailable")):
        with pytest.raises(OSError, match="native locking unavailable"):
            catalogue.delete(snapshot)
    assert (catalogue.path_catalogue / snapshot.id / snapshot.directories[0].directory_name / "identity").read_bytes() == b"preserved"
    assert catalogue.get_by_id(snapshot.id) is not None


def _read_after_fork(path: Path, connection) -> None:
    """Report whether a forked worker incorrectly inherited its parent's active operation lease."""
    try:
        SnapshotCatalogue(path).get_all()
    except SnapshotBusyError:
        connection.send(True)
    else:
        connection.send(False)
    finally:
        connection.close()


@pytest.mark.skipif(not hasattr(os, "fork"), reason="native fork is unavailable")
def test_forked_worker_cannot_inherit_parent_operation_ownership(snapshot_workspace: Path) -> None:
    """A multiprocessing fork must contend independently rather than reenter its parent's lease."""
    catalogue = SnapshotCatalogue(snapshot_workspace / "catalogue", SnapshotSettings())
    observed = []

    def inspect(_percentage):
        """Fork while a real journal is live and wait for a bounded competing metadata query."""
        if observed:
            return
        context = multiprocessing.get_context("fork")
        parent, child = context.Pipe()
        process = context.Process(target=_read_after_fork, args=(catalogue.path_catalogue, child))
        try:
            process.start()
            child.close()
            assert parent.poll(10), "forked reader did not finish"
            assert parent.recv() is True
            process.join(timeout=10)
            assert process.exitcode == 0
        finally:
            if process.is_alive():
                process.terminate()
                process.join(timeout=10)
            parent.close()
            child.close()
        observed.append(True)

    catalogue.add(_snapshot(snapshot_workspace, "forked"), progress_callback=inspect)
    assert observed
    assert catalogue.get_by_id("forked") is not None
