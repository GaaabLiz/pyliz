"""Rollback restores values without invalidating live model references."""

from pylizlib.core.os.snap.domain import SnapDirAssociation, Snapshot
from pylizlib.core.os.snap.model_state import CapturedContentState, restore_snapshot_model


def test_restore_reuses_live_associations_and_copies_mutable_state(tmp_path):
    """Kept IDs retain identity; added/removed IDs and nested manifests are restored."""
    kept = SnapDirAssociation(1, str(tmp_path / "live"), "kept")
    removed = SnapDirAssociation(2, str(tmp_path / "removed"), "removed")
    live = Snapshot("id", "requested", "", directories=[kept, removed], tags=["requested"])
    old_kept = SnapDirAssociation(5, str(tmp_path / "old"), "kept", integrity_manifest={".": {"type": "directory", "size": 0, "sha256": None}})
    old_kept._set_storage_name("legacy-folder")
    old_added = SnapDirAssociation(6, str(tmp_path / "added"), "added")
    previous = Snapshot("id", "persisted", "", directories=[old_kept, old_added], tags=["persisted"])
    original_list = live.directories

    restore_snapshot_model(live, previous)

    assert live.name == "persisted"
    assert live.directories is original_list
    assert live.directories[0] is kept
    assert [association.folder_id for association in live.directories] == ["kept", "added"]
    assert kept.index == 5
    assert kept.directory_name == "legacy-folder"
    assert kept.integrity_manifest == old_kept.integrity_manifest
    assert kept.integrity_manifest is not old_kept.integrity_manifest
    assert kept.integrity_manifest["."] is not old_kept.integrity_manifest["."]
    assert live.directories[1] is not old_added
    assert live.tags is not previous.tags


def test_field_iterator_is_reused_for_every_matching_association(tmp_path):
    """A single-pass field iterable still restores all retained associations."""
    live = Snapshot("id", "live", "", directories=[SnapDirAssociation(1, str(tmp_path), "a"), SnapDirAssociation(2, str(tmp_path), "b")])
    previous = Snapshot("id", "old", "", directories=[SnapDirAssociation(3, str(tmp_path), "a"), SnapDirAssociation(4, str(tmp_path), "b")])
    restore_snapshot_model(live, previous, association_fields=iter(["index"]))
    assert [association.index for association in live.directories] == [3, 4]


def test_acquisition_state_restores_original_references_and_only_capture_fields(tmp_path):
    """Partial capture rollback must not turn into complete model restoration."""
    association = SnapDirAssociation(1, str(tmp_path), "association", integrity_manifest={".": {"type": "directory", "size": 0, "sha256": None}})
    snapshot = Snapshot("id", "before", "", directories=[association])
    original_manifest = association.integrity_manifest
    state = CapturedContentState.capture(snapshot)
    snapshot.name = "after"
    association.integrity_manifest = None
    association.mb_size = 10
    state.restore_associations(snapshot)
    state.restore_capture_interval(snapshot)
    assert snapshot.name == "after"
    assert association.integrity_manifest is original_manifest
    assert association.mb_size == 0


def test_create_logs_the_committed_snapshot(tmp_path, caplog):
    """Create reports success only after staging and publication complete."""
    from pylizlib.core.os.snap.manager import SnapshotManager

    manager = SnapshotManager(Snapshot("logged", "name", ""), tmp_path / "catalogue")
    with caplog.at_level("INFO", logger="PylizLib"):
        manager.create()
    assert "Creating snapshot id=logged associations=0" in caplog.text
    assert "Created snapshot id=logged" in caplog.text
