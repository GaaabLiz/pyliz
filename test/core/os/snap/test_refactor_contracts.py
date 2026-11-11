"""Characterize public effects that must survive the internal snapshot refactor.

These tests deliberately include existing failure and merge semantics. They are
compatibility checks, not proposals for stronger transactional guarantees.
"""

import importlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest

from pylizlib.core.os import snap as api
from pylizlib.core.os.snap.domain import SnapDirAssociation, Snapshot, SnapshotSettings
from pylizlib.core.os.snap.manager import SnapshotManager
from pylizlib.core.os.snap.serializer import SnapshotSerializer


@pytest.fixture
def tmp_path():
    """Keep installation targets outside OS-protected temporary directories."""
    root = Path(__file__).resolve().parents[4] / "test_local"
    root.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix="snap_contract_", dir=root) as directory:
        yield Path(directory)


def stored_snapshot(tmp_path, snapshot_id="contract"):
    """Create one source and its stored snapshot without shared test directories."""
    source = tmp_path / f"source-{snapshot_id}"
    source.mkdir()
    (source / "value.txt").write_text("stored", encoding="utf-8")
    snapshot = Snapshot(
        id=snapshot_id,
        name=snapshot_id,
        desc="",
        directories=[SnapDirAssociation(1, str(source), "association")],
    )
    manager = SnapshotManager(snapshot, tmp_path / "catalogue", SnapshotSettings())
    manager.create()
    return source, snapshot, manager


def test_public_exports_keep_original_class_identity():
    """Package exports must refer to the same objects as the legacy modules."""
    for name in api.__all__:
        symbol = getattr(api, name)
        if hasattr(symbol, "__module__") and symbol.__module__.startswith("pylizlib"):
            assert getattr(importlib.import_module(symbol.__module__), name) is symbol
    assert api.SnapshotManager is SnapshotManager
    assert api.Snapshot is Snapshot


def test_partial_metadata_update_preserves_unknown_fields(tmp_path):
    """Updating a field must not deserialize or discard extension fields."""
    _, _, manager = stored_snapshot(tmp_path)
    data = json.loads(manager.path_snapshot_json.read_text())
    data["future_extension"] = {"nested": [1, 2]}
    manager.path_snapshot_json.write_text(json.dumps(data))
    SnapshotSerializer.update_field(manager.path_snapshot_json, "name", "renamed")
    assert json.loads(manager.path_snapshot_json.read_text())["future_extension"] == {"nested": [1, 2]}


def test_install_merge_replaces_colliding_top_level_directory(tmp_path):
    """The existing merge replaces whole colliding subdirectories at level one."""
    source, snapshot, manager = stored_snapshot(tmp_path)
    (source / "sub").mkdir()
    (source / "sub" / "stored.txt").write_text("stored")
    manager.update_associated_dirs_from_system()
    (source / "sub" / "live-only.txt").write_text("live")
    (source / "extra.txt").write_text("keep")
    assert manager.install(clear_destination=False) is None
    assert (source / "extra.txt").read_text() == "keep"
    assert not (source / "sub" / "live-only.txt").exists()
    assert (source / "sub" / "stored.txt").read_text() == "stored"
    assert snapshot.date_last_used is not None


def test_install_metadata_failure_leaves_published_contents(tmp_path):
    """Last-used persistence happens after publication and cannot roll it back."""
    source, snapshot, manager = stored_snapshot(tmp_path)
    (source / "value.txt").write_text("live")
    with patch.object(SnapshotSerializer, "update_field", side_effect=OSError("metadata failed")):
        with pytest.raises(OSError, match="metadata failed"):
            manager.install()
    assert (source / "value.txt").read_text() == "stored"
    assert snapshot.date_last_used is not None
    assert list(tmp_path.glob(f"{source.name}_bck_*"))


def test_callback_failure_during_create_does_not_publish(tmp_path):
    """An observer exception propagates and the new snapshot stays unpublished."""
    source = tmp_path / "source"
    source.mkdir()
    (source / "value").write_text("bytes")
    snapshot = Snapshot("observer", "observer", "", directories=[SnapDirAssociation(1, str(source), "a")])
    manager = SnapshotManager(snapshot, tmp_path / "catalogue", SnapshotSettings())

    def fail(_percentage):
        """Simulate an observer that fails during copying."""
        raise RuntimeError("observer failed")

    with pytest.raises(Exception, match="observer failed"):
        manager.create(progress_callback=fail)
    assert not manager.path_snapshot.exists()
    assert snapshot.directories[0].integrity_manifest is None
    assert list(manager.path_catalogue.iterdir()) == []


def test_search_cancellation_is_per_snapshot_and_precedes_current_file(tmp_path):
    """False cancels the current snapshot, while search_list attempts the next."""
    _, first, manager = stored_snapshot(tmp_path, "first")
    _, second, _ = stored_snapshot(tmp_path, "second")
    catalogue = api.SnapshotCatalogue(manager.path_catalogue)
    calls = []

    def cancel(name, total, processed):
        """Record notification arguments and cancel before reading the file."""
        calls.append((name, total, processed))
        return False

    results = api.SnapshotSearcher(catalogue).search_list(
        [first, second],
        api.SnapshotSearchParams("stored"),
        cancel,
    )
    assert results == []
    assert calls == [("value.txt", 1, 1), ("value.txt", 1, 1)]


def test_catalogue_reads_current_path_and_settings(tmp_path):
    """Changing catalogue location or backup flags affects subsequent calls."""
    _, snapshot, manager = stored_snapshot(tmp_path)
    settings = SnapshotSettings()
    catalogue = api.SnapshotCatalogue(tmp_path / "other", settings)
    assert catalogue.get_by_id(snapshot.id) is None
    catalogue.set_catalogue_path(manager.path_catalogue)
    assert catalogue.get_by_id(snapshot.id).id == snapshot.id
    settings.backup_path = tmp_path / "backups"
    settings.backup_pre_delete = True
    assert catalogue.delete(snapshot) is None
    assert len(list(settings.backup_path.glob("backup_beforeDelete_*.zip"))) == 1


def test_metadata_updates_keep_separate_ordered_writes(tmp_path):
    """Base fields and content data keep independent update_field operations."""
    _, _, manager = stored_snapshot(tmp_path)
    with patch.object(SnapshotSerializer, "update_field", wraps=SnapshotSerializer.update_field) as update:
        manager.update_json_base_fields()
        manager.update_json_data_fields()
    assert [call.args[1] for call in update.call_args_list] == [
        "name",
        "desc",
        "author",
        "tags",
        "date_modified",
        "data",
        "date_last_modified",
    ]


def test_edit_planner_resolves_legacy_rename_without_touching_storage(tmp_path):
    """Planning resolves names using persisted IDs and performs no publication."""
    from pylizlib.core.os.snap.domain import SnapEditAction, SnapEditType
    from pylizlib.core.os.snap.operations.edits import SnapshotEditPlanner

    _, snapshot, manager = stored_snapshot(tmp_path)
    before = manager.path_snapshot_json.read_bytes()
    original_name = snapshot.directories[0].directory_name
    snapshot.directories[0].index = 2
    plan = SnapshotEditPlanner(manager._storage()).build(
        [
            SnapEditAction(SnapEditType.RENAME_DIR, old_directory_name=original_name),
        ]
    )
    assert plan.old_json == before
    assert len(plan.moves) == 1
    assert plan.moves[0].source.name == original_name
    assert plan.moves[0].target.name == snapshot.directories[0].directory_name
    assert plan.moves[0].source.is_dir()
    assert not plan.moves[0].target.exists()
    assert manager.path_snapshot_json.read_bytes() == before


def test_editor_restores_exact_metadata_bytes_when_save_partially_fails(tmp_path):
    """A failed JSON rewrite restores whitespace as well as association names."""
    from pylizlib.core.os.snap.diff import get_edits_between_snapshots
    from pylizlib.core.os.snap.operations.edits import SnapshotEditor

    _, snapshot, manager = stored_snapshot(tmp_path)
    before = json.dumps(json.loads(manager.path_snapshot_json.read_text()), indent=2).encode()
    manager.path_snapshot_json.write_bytes(before)
    original = snapshot.clone()
    snapshot.directories[0].index = 2

    def fail_save(_snapshot, path):
        """Simulate an interrupted metadata rewrite after content publication."""
        path.write_bytes(b"partial")
        raise OSError("save failed")

    with patch.object(SnapshotSerializer, "to_json", side_effect=fail_save):
        with pytest.raises(OSError, match="save failed"):
            SnapshotEditor(manager._storage()).apply(get_edits_between_snapshots(original, snapshot))
    assert manager.path_snapshot_json.read_bytes() == before
    assert (manager.path_snapshot / original.directories[0].directory_name).is_dir()
    assert not (manager.path_snapshot / snapshot.directories[0].directory_name).exists()


def test_storage_context_rejects_mutated_snapshot_identity_and_json_filename(tmp_path):
    """Extracted storage checks retain the manager's captured destinations."""
    _, snapshot, manager = stored_snapshot(tmp_path)
    snapshot.id = "different"
    with pytest.raises(ValueError, match="ID changed"):
        manager._snapshot_root_path()
    snapshot.id = "contract"
    manager.settings.json_filename = "different.json"
    with pytest.raises(ValueError, match="JSON path changed"):
        manager._storage().save_json()
    assert not (manager.path_snapshot / "different.json").exists()


def test_installer_stages_all_targets_before_modifying_live_copies(tmp_path):
    """Failure on the second staged copy leaves both live directories untouched."""
    from pylizlib.core.os.snap.operations.install import SnapshotInstaller

    first, snapshot, manager = stored_snapshot(tmp_path)
    second = tmp_path / "second-source"
    second.mkdir()
    (second / "value.txt").write_text("second-stored")
    manager.install_directory(second)
    (first / "value.txt").write_text("first-live")
    (second / "value.txt").write_text("second-live")
    strategy = manager.settings.copy_strategy
    original_copy = strategy.copy_directory
    calls = []

    def fail_second(source, destination, *args, **kwargs):
        """Copy the first staging normally, then simulate a second-copy failure."""
        calls.append(source)
        if len(calls) == 2:
            raise OSError("second staging failed")
        return original_copy(source, destination, *args, **kwargs)

    with patch.object(strategy, "copy_directory", side_effect=fail_second):
        with pytest.raises(RuntimeError, match="second staging failed"):
            SnapshotInstaller(manager._storage()).install()
    assert (first / "value.txt").read_text() == "first-live"
    assert (second / "value.txt").read_text() == "second-live"
    assert snapshot.date_last_used is None
    assert list(tmp_path.glob("*_staging_*")) == []


def test_sync_failure_restores_copies_and_memory_without_rewriting_metadata_bytes(tmp_path):
    """Sync preserves its existing recovery boundary, distinct from edit rollback."""
    from pylizlib.core.os.snap.operations.sync import SnapshotSynchronizer

    source, snapshot, manager = stored_snapshot(tmp_path)
    association = snapshot.directories[0]
    old_manifest = association.integrity_manifest
    old_size = association.mb_size
    old_date = snapshot.date_last_modified
    (source / "value.txt").write_text("new live contents with a different size")

    def fail_save(_snapshot, path):
        """Interrupt a sync metadata write after the model has been updated."""
        path.write_bytes(b"partial sync metadata")
        raise OSError("sync metadata failed")

    with patch.object(SnapshotSerializer, "to_json", side_effect=fail_save):
        with pytest.raises(OSError, match="sync metadata failed"):
            SnapshotSynchronizer(manager._storage()).update_associated_dirs_from_system()
    stored = manager.path_snapshot / association.directory_name / "value.txt"
    assert stored.read_text() == "stored"
    assert association.integrity_manifest is old_manifest
    assert association.mb_size == old_size
    assert snapshot.date_last_modified == old_date
    assert manager.path_snapshot_json.read_bytes() == b"partial sync metadata"
    assert list(manager.path_snapshot.glob("*_bck_*")) == []


def test_lifecycle_metadata_failure_preserves_old_root_and_manifest_identity(tmp_path):
    """A replacement whose staged JSON fails never moves the original root."""
    from pylizlib.core.os.snap.operations.lifecycle import SnapshotLifecycle

    source, snapshot, manager = stored_snapshot(tmp_path)
    before = {p.relative_to(manager.path_snapshot): p.read_bytes() for p in manager.path_snapshot.rglob("*") if p.is_file()}
    manifest = snapshot.directories[0].integrity_manifest
    (source / "value.txt").write_text("new source data")
    with patch.object(SnapshotSerializer, "to_json", side_effect=OSError("staged JSON failed")):
        with pytest.raises(OSError, match="staged JSON failed"):
            SnapshotLifecycle(manager._storage()).create(replace_existing=True)
    assert {p.relative_to(manager.path_snapshot): p.read_bytes() for p in manager.path_snapshot.rglob("*") if p.is_file()} == before
    assert snapshot.directories[0].integrity_manifest is manifest
    assert list(manager.path_catalogue.iterdir()) == [manager.path_snapshot]


def test_catalogue_import_keeps_id_only_entries_and_continues_after_bad_json(tmp_path):
    """Batch import keeps its raw-ID policy instead of adding model validation."""
    import zipfile

    from pylizlib.core.os.snap.operations.transfers import CatalogueTransferService

    archive = tmp_path / "catalogue.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("bad/snapshot.json", "broken JSON")
        handle.writestr("minimal/snapshot.json", '{"id": "minimal"}')
        handle.writestr("minimal/payload", "kept")
    catalogue = api.SnapshotCatalogue(tmp_path / "imported")
    service = CatalogueTransferService(catalogue.path_catalogue, catalogue.settings, catalogue)
    assert service.import_catalogue(archive) is None
    assert (catalogue.path_catalogue / "minimal" / "payload").read_text() == "kept"
    assert not (catalogue.path_catalogue / "bad").exists()
    assert catalogue.get_by_id("minimal") is None  # its incomplete model is still unreadable
