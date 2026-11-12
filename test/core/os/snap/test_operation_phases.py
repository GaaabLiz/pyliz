"""Named phases retain each operation's distinct rollback and completion policy."""

from functools import partial
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pylizlib.core.os.snap.domain import Snapshot
from pylizlib.core.os.snap.manager import SnapshotManager
from pylizlib.core.os.snap.model_state import CapturedContentState
from pylizlib.core.os.snap.operations.edits import SnapshotEditor
from pylizlib.core.os.snap.operations.sync import SnapshotSynchronizer
from pylizlib.core.os.snap.storage.transactions import TransactionRecoveryError


@pytest.mark.parametrize("operation", ["edit", "sync"])
def test_failed_rollback_keeps_original_failure_as_cause(tmp_path, operation):
    """An incomplete rollback must not replace the original operation failure."""
    original = OSError("original failure")
    journal = SimpleNamespace(path=tmp_path / "journal.json", decide_rollback=Mock(side_effect=OSError("rollback failed")))
    storage = SimpleNamespace(snapshot=SimpleNamespace(name="requested"))
    if operation == "edit":
        expected_error = TransactionRecoveryError
        execute = partial(SnapshotEditor(storage)._rollback_failed_edit, journal, SimpleNamespace(old_snapshot=None), original)
    else:
        expected_error = RuntimeError
        execute = partial(SnapshotSynchronizer(storage)._rollback_failed_sync, journal, CapturedContentState({}, (None, None)), None, original)

    with pytest.raises(expected_error, match="journal retained") as error:
        execute()
    assert error.value.__cause__ is original
    assert storage.snapshot.name == "requested"
    journal.decide_rollback.assert_called_once_with(storage)


def test_sync_and_edit_log_only_completed_operations(tmp_path, caplog):
    """Zero-association operations still persist metadata and report their outcomes."""
    manager = SnapshotManager(Snapshot("empty", "name", ""), tmp_path / "catalogue")
    manager.create()
    with caplog.at_level("INFO", logger="PylizLib"):
        manager.update_associated_dirs_from_system()
        manager.update_from_actions_list([])
    for event in ("Synchronizing snapshot id=empty", "Synchronized snapshot id=empty", "Editing snapshot id=empty", "Edited snapshot id=empty"):
        assert event in caplog.text
