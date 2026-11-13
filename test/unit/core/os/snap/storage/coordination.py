"""Operation ownership separates current work from abandoned transaction intent."""

from unittest.mock import patch

import pytest

from pylizlib.core.os.filesystem.locking import FileLock, FileLockBusyError
from pylizlib.core.os.snap.storage.coordination import catalogue_access, is_active_journal, observer_callback
from pylizlib.core.os.snap.storage.paths import assert_no_operational_storage, get_snapshot_path
from pylizlib.core.os.snap.storage.transactions import SnapshotTransactionJournal, recover_pending_transactions


@pytest.mark.parametrize("termination", [RuntimeError, SystemExit])
def test_abandoned_active_journal_becomes_recoverable_after_operation_exit(tmp_path, termination):
    """Implicit lookup skips live intent; exceptional exit removes only in-memory ownership."""
    with pytest.raises(termination):
        with catalogue_access(tmp_path):
            journal = SnapshotTransactionJournal.begin(tmp_path, "snapshot_tree", {"snapshot_id": "new", "had_original": False})
            staged = journal.workspace / "snapshot"
            staged.mkdir()
            (staged / "payload").write_bytes(b"owned staging")
            assert is_active_journal(journal.workspace)
            assert recover_pending_transactions(tmp_path) == []
            assert (staged / "payload").read_bytes() == b"owned staging"
            raise termination("simulated interruption")
    assert not is_active_journal(journal.workspace)
    assert recover_pending_transactions(tmp_path) == ["snapshot_tree"]
    assert not journal.workspace.exists()
    assert recover_pending_transactions(tmp_path) == []


def test_native_lock_failure_prevents_journal_creation(tmp_path):
    """A storage lacking native locking must never silently proceed with only a thread lock."""
    with patch.object(FileLock, "_acquire", side_effect=OSError("locking unavailable")):
        with pytest.raises(OSError, match="locking unavailable"):
            with catalogue_access(tmp_path):
                SnapshotTransactionJournal.begin(tmp_path, "snapshot_tree")
    assert not (tmp_path / ".pyliz_transactions").exists()
    with catalogue_access(tmp_path):
        assert not (tmp_path / ".pyliz_transactions").exists()


def test_failed_nested_operation_does_not_hide_abandoned_intent_from_a_later_step(tmp_path):
    """A batch retaining the catalogue gate must still recover an earlier failed entry."""
    with catalogue_access(tmp_path):
        with pytest.raises(RuntimeError, match="entry failed"):
            with catalogue_access(tmp_path):
                journal = SnapshotTransactionJournal.begin(tmp_path, "snapshot_tree", {"snapshot_id": "failed", "had_original": False})
                assert recover_pending_transactions(tmp_path) == []
                raise RuntimeError("entry failed")
        assert not is_active_journal(journal.workspace)
        assert recover_pending_transactions(tmp_path) == ["snapshot_tree"]
        assert not journal.workspace.exists()


def test_observer_context_restores_after_an_exception(tmp_path):
    """A failed observer cannot leave later ordinary operations incorrectly marked as callbacks."""

    def fail():
        """Raise the exact failure object so wrapper behavior remains transparent."""
        raise failure

    failure = RuntimeError("observer failed")
    with pytest.raises(RuntimeError) as result:
        observer_callback(fail)()
    assert result.value is failure
    with catalogue_access(tmp_path):
        assert observer_callback(lambda value: value)(42) == 42


def test_operation_errors_are_not_rewritten_as_acquisition_errors(tmp_path):
    """Only contention during gate acquisition is translated to the public busy error."""
    failure = FileLockBusyError("delegate or observer failure")
    with pytest.raises(FileLockBusyError) as result:
        with catalogue_access(tmp_path):
            raise failure
    assert result.value is failure


@pytest.mark.parametrize("name", [".pyliz_snapshot.lock", ".PYLIZ_SNAPSHOT.LOCK", ".pyliz_snapshot.lock. "])
def test_lock_namespace_is_rejected_for_ids_and_import_roots(tmp_path, name):
    """Imported data cannot replace the stable coordination inode, including portable aliases."""
    with pytest.raises(ValueError, match="reserved"):
        get_snapshot_path(name, tmp_path)
    (tmp_path / name).write_bytes(b"untrusted lock")
    with pytest.raises(ValueError, match="catalogue lock"):
        assert_no_operational_storage(tmp_path)


def test_nested_association_lock_filename_remains_ordinary_user_data(tmp_path):
    """Only direct operational entries are reserved; association files are preserved verbatim."""
    path = tmp_path / "association/.pyliz_snapshot.lock"
    path.parent.mkdir()
    path.write_bytes(b"user content")
    assert assert_no_operational_storage(tmp_path) is None
    assert path.read_bytes() == b"user content"
