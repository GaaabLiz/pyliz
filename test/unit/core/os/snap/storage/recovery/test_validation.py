"""Operation-specific validation retains error order without mutating journal data."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from pylizlib.core.os.snap.domain import SnapDirAssociation, Snapshot
from pylizlib.core.os.snap.storage.recovery.edits import _validate_edit
from pylizlib.core.os.snap.storage.recovery.replacements import _validate_replacement_entries
from pylizlib.core.os.snap.storage.transactions import TransactionRecoveryError


@pytest.fixture
def sync_record(tmp_path):
    """Provide a valid direct-child sync record without creating any stored tree."""
    association = SnapDirAssociation(1, str(tmp_path / "live"), "association")
    snapshot = Snapshot("snapshot", "name", "", directories=[association])
    root = tmp_path / "snapshot"
    storage = SimpleNamespace(snapshot=snapshot, path_snapshot=root, path_snapshot_json=root / "snapshot.json")
    entry = {
        "folder_id": association.folder_id,
        "stage": str(root / f"{association.directory_name}_staging_test"),
        "destination": str(root / association.directory_name),
        "backup": str(root / f"{association.directory_name}_bck_test"),
        "had_original": True,
    }
    return storage, {"entries": [entry], "staging_roots": [entry["stage"]]}


def test_sync_record_validation_is_repeatable_and_does_not_mutate(sync_record, tmp_path):
    """A validator instance belongs to one call; accepted JSON remains unchanged."""
    storage, data = sync_record
    original = deepcopy(data)
    _validate_replacement_entries("sync", data, storage, tmp_path)
    _validate_replacement_entries("sync", data, storage, tmp_path)
    assert data == original
    assert not storage.path_snapshot.exists()


@pytest.mark.parametrize("invalid", ["unknown", "merge", "outside", "name", "roots"])
def test_replacement_validation_preserves_first_failure(sync_record, tmp_path, invalid):
    """Shape, association identity and operation paths retain their original priority."""
    storage, data = sync_record
    entry = data["entries"][0]
    if invalid == "unknown":
        entry.update(folder_id="missing", stage=None)
        expected = "Unknown association"
    elif invalid == "merge":
        entry.update(merge_child=True, stage_root=10)
        expected = "Only install journals"
    elif invalid == "outside":
        entry["stage"] = str(tmp_path / "outside")
        expected = "direct children"
    elif invalid == "name":
        entry["stage"] = str(storage.path_snapshot / "unexpected")
        expected = "unexpected staging or backup name"
    else:
        data["staging_roots"] = {}
        expected = "staging roots must be a list"
    with pytest.raises(TransactionRecoveryError, match=expected):
        _validate_replacement_entries("sync", data, storage, tmp_path)


def test_edit_duplicate_sets_are_local_to_one_plan(tmp_path):
    """Repeated validation is allowed, but duplicate sources in one plan are rejected."""
    storage = SimpleNamespace(path_snapshot_json=tmp_path / "snapshot.json")
    data = {"phase": "publishing", "moves": [{"source": "a", "target": "b", "staged": "original_0"}], "additions": [{"target": "c", "staged": "addition_0"}]}
    original = deepcopy(data)
    _validate_edit(data, storage, tmp_path)
    _validate_edit(data, storage, tmp_path)
    assert data == original
    data["moves"].append({"source": "a", "target": "d", "staged": "original_1"})
    with pytest.raises(TransactionRecoveryError, match="duplicate source names"):
        _validate_edit(data, storage, tmp_path)


def test_standalone_restore_recovery_refuses_a_changed_linked_parent(tmp_path):
    """A moved parent cannot redirect rollback into another user's directory."""
    from pylizlib.core.os.snap.storage.transactions import SnapshotTransactionJournal, TransactionRecoveryError

    catalogue = tmp_path / "catalogue"
    catalogue.mkdir()
    parent = tmp_path / "parent"
    parent.mkdir()
    backup = parent / "target_bck_test"
    backup.mkdir()
    (backup / "old").write_bytes(b"recoverable original")
    destination = parent / "target"
    journal = SnapshotTransactionJournal.begin(
        catalogue,
        "restore_associations_manifest",
        {"entries": [{"folder_id": "folder", "stage": str(parent / "target_staging_test"), "destination": str(destination), "backup": str(backup), "had_original": True}]},
    )
    moved = tmp_path / "moved"
    parent.rename(moved)
    foreign = tmp_path / "foreign"
    (foreign / "target").mkdir(parents=True)
    (foreign / "target/important").write_bytes(b"foreign data")
    try:
        parent.symlink_to(foreign, target_is_directory=True)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"directory symlinks are unavailable: {error}")
    with pytest.raises(TransactionRecoveryError, match="unsafe parent"):
        journal.recover()
    assert journal.path.is_file()
    assert (moved / "target_bck_test/old").read_bytes() == b"recoverable original"
    assert (foreign / "target/important").read_bytes() == b"foreign data"
