"""Exercise each recovery decision through the compatibility entry point."""

import pytest

from pylizlib.core.os.snap.storage.transactions import SnapshotTransactionJournal, recover_pending_transactions


@pytest.mark.parametrize("state", ["prepared", "rollback_decided", "commit_decided", "committed"])
def test_snapshot_tree_recovery_is_repeatable(tmp_path, state, caplog):
    """A full-tree journal rolls back or commits according to its durable decision."""
    scope = tmp_path / "catalogue"
    scope.mkdir()
    journal = SnapshotTransactionJournal.begin(scope, "snapshot_tree", {"snapshot_id": "snapshot", "had_original": False})
    stage = journal.workspace / "snapshot"
    stage.mkdir()
    (stage / "content").write_text("new")
    destination = scope / "snapshot"
    if state == "committed":
        stage.rename(destination)
    journal.set_state(state)

    with caplog.at_level("INFO", logger="PylizLib"):
        assert recover_pending_transactions(scope) == ["snapshot_tree"]
        assert recover_pending_transactions(scope) == []

    assert destination.exists() is (state in {"commit_decided", "committed"})
    if destination.exists():
        assert (destination / "content").read_text() == "new"
    assert not journal.workspace.exists()
    assert caplog.text.count("Recovering snapshot operation=snapshot_tree") == 1
    assert caplog.text.count("Recovered snapshot operation=snapshot_tree") == 1


@pytest.mark.parametrize("state", ["prepared", "rollback_decided", "commit_decided", "committed"])
def test_standalone_manifest_restore_preserves_the_decided_version(tmp_path, state):
    """AD recovery outside the catalogue requires no snapshot metadata context."""
    scope = tmp_path / "catalogue"
    scope.mkdir()
    target = tmp_path / "live"
    stage = tmp_path / "live_staging_test"
    backup = tmp_path / "live_bck_test"
    target.mkdir()
    stage.mkdir()
    (target / "content").write_text("old")
    (stage / "content").write_text("new")
    entry = {"folder_id": "stable", "stage": str(stage), "destination": str(target), "backup": str(backup), "had_original": True}
    journal = SnapshotTransactionJournal.begin(scope, "restore_associations_manifest", {"entries": [entry]})
    if state != "commit_decided":
        target.rename(backup)
        stage.rename(target)
    journal.set_state(state)

    assert recover_pending_transactions(scope) == ["restore_associations_manifest"]
    assert recover_pending_transactions(scope) == []
    expected = "new" if state in {"commit_decided", "committed"} else "old"
    assert (target / "content").read_text() == expected
    assert not stage.exists()
    assert not backup.exists()


def test_journal_logs_only_persisted_decisions(tmp_path, monkeypatch, caplog):
    """A failed decision write must not emit a successful persistence message."""
    journal = SnapshotTransactionJournal(tmp_path, {"state": "prepared"})

    def failed_write():
        """Simulate a failed durable decision without changing the visible outcome."""
        raise OSError("journal persistence failed")

    monkeypatch.setattr(journal, "_write", failed_write)
    with caplog.at_level("DEBUG", logger="PylizLib"):
        with pytest.raises(OSError, match="persistence failed"):
            journal.set_state("committed")
    assert "decision=committed" not in caplog.text
