"""Interrupt rollback itself, including overlapping legacy directory names."""

import json
from dataclasses import dataclass
from unittest.mock import patch

import pytest

from pylizlib.core.os.snap import SnapDirAssociation, Snapshot, SnapshotSerializer, SnapshotSettings
from pylizlib.core.os.snap.storage.context import SnapshotStorage
from pylizlib.core.os.snap.storage.recovery import edit_rollback
from pylizlib.core.os.snap.storage.transactions import SnapshotTransactionJournal, TransactionRecoveryError, prepare_snapshot_metadata, recover_storage_transactions


@dataclass
class EditScenario:
    """Own one isolated journal, its original model and exact old JSON bytes."""

    storage: SnapshotStorage
    journal: SnapshotTransactionJournal
    old_json: bytes


def _scenario(tmp_path, plan, *, state="prepared", legacy=False):
    """Construct a valid interrupted publication with distinct original payloads."""
    catalogue = tmp_path / "catalogue"
    root = catalogue / "snapshot"
    root.mkdir(parents=True)
    snapshot = Snapshot("snapshot", "old", "original description", directories=[SnapDirAssociation(index, str(tmp_path / f"live-{name}"), name) for index, name in enumerate(("A", "B"))])
    metadata_path = root / "snapshot.json"
    SnapshotSerializer.to_json(snapshot, metadata_path)
    data = json.loads(metadata_path.read_text())
    for item, name in zip(data["directories"], ("A", "B")):
        item["storage_name"] = name
        (root / name / "empty").mkdir(parents=True)
        (root / name / "identity").write_bytes(f"old-{name}".encode())
    SnapshotSerializer.write_text(metadata_path, json.dumps(data))
    snapshot = SnapshotSerializer.from_json(metadata_path)
    storage = SnapshotStorage(snapshot, SnapshotSettings(), catalogue, root, metadata_path)
    first_target = "B" if plan == "cycle" else None
    moves = [{"source": "A", "target": first_target, "staged": "original_0"}]
    additions = []
    if plan in {"cycle", "reuse-removed"}:
        moves.append({"source": "B", "target": "A", "staged": "original_1"})
    elif plan == "addition-reuses-removed":
        additions.append({"target": "A", "staged": "addition_0"})
    elif plan == "nonoverlap":
        moves[0]["target"] = "C"
    payload = {"phase": "publishing", "moves": moves, "additions": additions}
    if not legacy:
        payload["rollback_phase"] = "not_started"
    journal = SnapshotTransactionJournal.begin(root, "edit", payload)
    if legacy:
        journal.payload["version"] = 1
        journal.payload["payload"].pop("rollback_phase", None)
        journal._write()
    old_json = metadata_path.read_bytes()
    journal.update_payload(metadata=prepare_snapshot_metadata(storage, journal.workspace))
    for move in moves:
        (root / move["source"]).rename(journal.workspace / move["staged"])
    for move in moves:
        if move["target"] is not None:
            (journal.workspace / move["staged"]).rename(root / move["target"])
    for addition in additions:
        (root / addition["target"]).mkdir()
        (root / addition["target"] / "identity").write_bytes(b"new addition")
    if state == "rollback_decided":
        journal.set_state(state)
        SnapshotSerializer.update_field(metadata_path, "desc", "interrupted new metadata")
    return EditScenario(storage, journal, old_json)


def _assert_originals(scenario):
    """Verify association identity, empty directories, metadata and completed cleanup."""
    root = scenario.storage.path_snapshot
    assert (root / "A/identity").read_bytes() == b"old-A"
    assert (root / "B/identity").read_bytes() == b"old-B"
    assert (root / "A/empty").is_dir() and (root / "B/empty").is_dir()
    assert not (root / "C").exists()
    assert scenario.storage.path_snapshot_json.read_bytes() == scenario.old_json
    assert not list(root.rglob("journal.json"))


@pytest.mark.parametrize("plan", ["cycle", "reuse-removed", "addition-reuses-removed", "nonoverlap"])
@pytest.mark.parametrize("state", ["prepared", "rollback_decided"])
@pytest.mark.parametrize("partial_cleanup", [False, True])
def test_repeated_rollback_after_cleanup_interruption_preserves_originals(tmp_path, plan, state, partial_cleanup):
    """A restored original can never be mistaken for a still-published target."""
    scenario = _scenario(tmp_path, plan, state=state)

    def stop_cleanup(journal):
        """Optionally remove disposable metadata before simulating another crash."""
        if partial_cleanup:
            (journal.workspace / "metadata-old.json").unlink()
            if (journal.workspace / "addition_0/identity").exists():
                (journal.workspace / "addition_0/identity").unlink()
        raise SystemExit("interrupted cleanup")

    with patch.object(SnapshotTransactionJournal, "cleanup", stop_cleanup):
        with pytest.raises(SystemExit, match="interrupted cleanup"):
            recover_storage_transactions(scenario.storage)
    assert (scenario.storage.path_snapshot / "A/identity").read_bytes() == b"old-A"
    recover_storage_transactions(scenario.storage)
    recover_storage_transactions(scenario.storage)
    _assert_originals(scenario)


RENAME_INTERRUPTS = [(plan, index) for plan, count in [("cycle", 4), ("reuse-removed", 3), ("addition-reuses-removed", 2), ("nonoverlap", 2)] for index in range(1, count + 1)]


@pytest.mark.parametrize(("plan", "interruption"), RENAME_INTERRUPTS)
def test_rollback_resumes_after_each_individual_rename(tmp_path, plan, interruption):
    """Every namespace change may be the last completed action before restart."""
    scenario = _scenario(tmp_path, plan, state="rollback_decided")
    rename = edit_rollback.rename_and_sync
    calls = 0

    def stop_after_rename(source, destination):
        """Perform the rename and then terminate at the chosen durable boundary."""
        nonlocal calls
        rename(source, destination)
        calls += 1
        if calls == interruption:
            raise SystemExit("interrupted rename")

    with patch.object(edit_rollback, "rename_and_sync", side_effect=stop_after_rename):
        with pytest.raises(SystemExit, match="interrupted rename"):
            recover_storage_transactions(scenario.storage)
    recover_storage_transactions(scenario.storage)
    _assert_originals(scenario)


@pytest.mark.parametrize("phase", ["parking", "restoring", "restored"])
@pytest.mark.parametrize("published", [False, True])
def test_retrying_the_same_journal_after_a_phase_write_failure_is_safe(tmp_path, phase, published):
    """A proposed in-memory phase must become durable before its dependent actions."""
    scenario = _scenario(tmp_path, "reuse-removed", state="rollback_decided")
    write = SnapshotTransactionJournal._write
    failed = False

    def fail_once(journal):
        """Fail before or after marker publication while retaining the live object."""
        nonlocal failed
        if journal.payload["payload"].get("rollback_phase") == phase and not failed:
            failed = True
            if published:
                write(journal)
            raise OSError("marker persistence interrupted")
        write(journal)

    with patch.object(SnapshotTransactionJournal, "_write", fail_once):
        with pytest.raises(OSError, match="marker persistence interrupted"):
            scenario.journal.recover(scenario.storage)
    scenario.journal.recover(scenario.storage)
    _assert_originals(scenario)


@pytest.mark.parametrize("plan", ["cycle", "reuse-removed", "addition-reuses-removed"])
def test_ambiguous_legacy_overlap_preserves_every_remaining_entry(tmp_path, plan):
    """Old journals lacking progress cannot establish whether rollback already restored names."""
    scenario = _scenario(tmp_path, plan, legacy=True)
    if plan == "addition-reuses-removed":
        # Emulate an old rollback that restored A but never recorded that progress.
        root = scenario.storage.path_snapshot
        (root / "A").rename(scenario.journal.workspace / "addition_0")
        (scenario.journal.workspace / "original_0").rename(root / "A")
    before = {path.relative_to(scenario.storage.path_snapshot): path.read_bytes() for path in scenario.storage.path_snapshot.rglob("*") if path.is_file()}
    with pytest.raises(TransactionRecoveryError, match="[Ll]egacy.*overlap"):
        recover_storage_transactions(scenario.storage)
    assert {path.relative_to(scenario.storage.path_snapshot): path.read_bytes() for path in scenario.storage.path_snapshot.rglob("*") if path.is_file()} == before


def test_legacy_nonoverlapping_edit_remains_recoverable(tmp_path):
    """Unambiguous old rename journals retain automatic rollback compatibility."""
    scenario = _scenario(tmp_path, "nonoverlap", legacy=True)
    recover_storage_transactions(scenario.storage)
    _assert_originals(scenario)


def test_legacy_overlap_with_all_originals_staged_remains_recoverable(tmp_path):
    """An old addition reusing a removed name is unambiguous before any original restoration."""
    scenario = _scenario(tmp_path, "addition-reuses-removed", legacy=True)
    recover_storage_transactions(scenario.storage)
    _assert_originals(scenario)


def test_conflicting_original_and_staged_copy_are_both_retained(tmp_path):
    """A restoring marker must not authorize overwriting another existing source."""
    scenario = _scenario(tmp_path, "reuse-removed")
    scenario.journal.update_payload(rollback_phase="restoring")
    root = scenario.storage.path_snapshot
    published = (root / "A/identity").read_bytes()
    original = (scenario.journal.workspace / "original_0/identity").read_bytes()
    with pytest.raises(TransactionRecoveryError, match="Cannot determine"):
        recover_storage_transactions(scenario.storage)
    assert (root / "A/identity").read_bytes() == published
    assert (scenario.journal.workspace / "original_0/identity").read_bytes() == original
    assert scenario.journal.path.exists()


@pytest.mark.parametrize("phase", ["unknown", {}, []])
def test_invalid_rollback_progress_is_rejected_without_moving_data(tmp_path, phase):
    """Malformed progress must fail closed with the journal and all copies intact."""
    scenario = _scenario(tmp_path, "reuse-removed")
    scenario.journal.update_payload(rollback_phase=phase)
    before = {path.relative_to(scenario.storage.path_snapshot): path.read_bytes() for path in scenario.storage.path_snapshot.rglob("*") if path.is_file()}
    with pytest.raises(TransactionRecoveryError, match="invalid rollback phase"):
        recover_storage_transactions(scenario.storage)
    assert {path.relative_to(scenario.storage.path_snapshot): path.read_bytes() for path in scenario.storage.path_snapshot.rglob("*") if path.is_file()} == before


def test_commit_decision_cannot_resume_a_started_rollback(tmp_path):
    """Contradictory durable intent never authorizes publishing or deleting remaining copies."""
    scenario = _scenario(tmp_path, "reuse-removed")
    scenario.journal.update_payload(rollback_phase="restoring")
    scenario.journal.set_state("commit_decided")
    with pytest.raises(TransactionRecoveryError, match="rollback"):
        recover_storage_transactions(scenario.storage)
    assert scenario.journal.path.exists()
