"""Named phases retain each operation's distinct rollback and completion policy."""

from functools import partial
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pylizlib.core.os.snap.catalogue import SnapshotCatalogue
from pylizlib.core.os.snap.domain import BackupType, Snapshot, SnapshotSettings
from pylizlib.core.os.snap.manager import SnapshotManager
from pylizlib.core.os.snap.model_state import CapturedContentState
from pylizlib.core.os.snap.operations.edits import SnapshotEditor
from pylizlib.core.os.snap.operations.sync import SnapshotSynchronizer
from pylizlib.core.os.snap.searcher import SnapshotSearcher, SnapshotSearchParams, _ResultPage
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


def test_import_restore_and_search_logs_omit_query_and_contents(tmp_path, caplog):
    """Operation logs identify committed work without recording the search query."""
    manager = SnapshotManager(Snapshot("logged", "name", ""), tmp_path / "source-catalogue", SnapshotSettings())
    manager.create()
    archive = manager.create_backup(tmp_path / "backups", "", BackupType.SNAPSHOT_DIRECTORY)
    target = tmp_path / "target-catalogue"
    target.mkdir()
    catalogue = SnapshotCatalogue(target, SnapshotSettings())
    with caplog.at_level("DEBUG", logger="PylizLib"):
        catalogue.import_snapshot(archive)
        catalogue.restore_backup(archive)
        snapshot = catalogue.get_by_id("logged")
        SnapshotSearcher(catalogue).search(snapshot, SnapshotSearchParams("private-query-marker"))
    assert "Imported snapshot id=logged" in caplog.text
    assert "Restored backup snapshot=logged type=SNAPSHOT_DIRECTORY" in caplog.text
    assert "Finished snapshot search snapshot=logged results=0" in caplog.text
    assert "private-query-marker" not in caplog.text


def test_chunk_observer_truthiness_is_checked_at_each_chunk(tmp_path):
    """Adapters preserve custom observer truthiness without an extra initial check."""

    class AlternatingObserver:
        """Enable every second notification through a stateful truthiness check."""

        checks = 0
        calls = 0

        def __bool__(self):
            """Record one truthiness check for each decoded chunk."""
            self.checks += 1
            return self.checks % 2 == 0

        def __call__(self, name, total, processed):
            """Count enabled notifications without cancelling the file scan."""
            self.calls += 1

    path = tmp_path / "text"
    path.write_text("abcdef", encoding="utf-8")
    observer = AlternatingObserver()
    SnapshotSearcher(None)._search_in_file(path, SnapshotSearchParams("absent", chunk_size=1), None, "snapshot", _ResultPage(0, 10), observer, 1, 1)
    assert observer.checks == 6
    assert observer.calls == 3
