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


@pytest.mark.parametrize("source_alias", [False, True])
def test_create_rejects_catalogue_inside_source_before_creating_staging(tmp_path, source_alias):
    """Catalogue staging cannot become part of an association source tree."""
    source = tmp_path / "project"
    source.mkdir()
    important = source / "important.txt"
    important.write_text("preserve")
    source_path = source
    if source_alias:
        source_path = tmp_path / "project-alias"
        try:
            source_path.symlink_to(source, target_is_directory=True)
        except (NotImplementedError, OSError) as error:
            pytest.skip(f"symlink creation is unavailable: {error}")

    catalogue = source / "snapshots"
    snapshot = Snapshot(
        f"nested-catalogue-{source_alias}",
        "nested catalogue",
        "",
        directories=[SnapDirAssociation(1, str(source_path), "project")],
    )
    manager = SnapshotManager(snapshot, catalogue, SnapshotSettings())

    with pytest.raises(ValueError, match="Copy destination .* is inside source directory"):
        manager.create()

    assert important.read_text() == "preserve"
    assert not catalogue.exists()


def test_snapshot_tree_publication_rejects_catalogue_inside_source(tmp_path):
    """Whole-tree publication rejects recursive catalogues before journaling."""
    from pylizlib.core.os.snap.storage.publication import publish_snapshot_tree

    source = tmp_path / "project"
    source.mkdir()
    (source / "important.txt").write_text("preserve")
    catalogue = source / "snapshots"

    with pytest.raises(ValueError, match="Copy destination .* is inside source directory"):
        publish_snapshot_tree(source, "copy", catalogue)

    assert (source / "important.txt").read_text() == "preserve"
    assert not catalogue.exists()


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


@pytest.mark.parametrize("clear_destination", [True, False])
@pytest.mark.parametrize("same_path", [True, False])
def test_install_rejects_coincident_or_nested_targets_before_staging(tmp_path, clear_destination, same_path):
    """Overlapping associations fail before either live destination changes."""
    root = tmp_path / "data"
    parent = root / "progetto"
    child = parent / "cache"
    child.mkdir(parents=True)
    (parent / "project.txt").write_text("snapshot project")
    (child / "cache.txt").write_text("snapshot cache")
    child_path = parent if same_path else child
    snapshot = Snapshot(
        f"overlap-{clear_destination}-{same_path}",
        "overlap",
        "",
        directories=[
            SnapDirAssociation(1, str(parent), "parent"),
            SnapDirAssociation(2, str(child_path), "child"),
        ],
    )
    manager = SnapshotManager(snapshot, tmp_path / "catalogue", SnapshotSettings())
    manager.create()
    (parent / "project.txt").write_text("live project")
    (child / "cache.txt").write_text("live cache")
    before = {path.relative_to(parent): path.read_bytes() for path in parent.rglob("*") if path.is_file()}

    with pytest.raises(ValueError, match="cannot be coincident or nested"):
        manager.install(clear_destination=clear_destination)

    assert {path.relative_to(parent): path.read_bytes() for path in parent.rglob("*") if path.is_file()} == before
    assert list(tmp_path.rglob("*_staging_*")) == []
    assert list(tmp_path.rglob("*_bck_*")) == []
    assert not (manager.path_snapshot / ".pyliz_transactions").exists()


def test_install_metadata_failure_leaves_published_contents(tmp_path):
    """A post-commit metadata failure is typed and leaves a recovery copy."""
    source, snapshot, manager = stored_snapshot(tmp_path)
    (source / "value.txt").write_text("live")
    from pylizlib.core.os.snap import SnapshotInstallMetadataError

    write_bytes = SnapshotSerializer.write_bytes

    def fail_active_metadata(path, contents):
        """Fail the active JSON publication after installation has committed."""
        if path == manager.path_snapshot_json:
            assert (source / "value.txt").read_text() == "stored"
            raise OSError("metadata failed")
        return write_bytes(path, contents)

    with patch.object(SnapshotSerializer, "write_bytes", side_effect=fail_active_metadata):
        with pytest.raises(SnapshotInstallMetadataError, match="contents were installed") as raised:
            manager.install()
    assert (source / "value.txt").read_text() == "stored"
    assert raised.value.installation_completed is True
    assert raised.value.metadata_field == "date_last_used"
    assert raised.value.metadata_published is None
    assert isinstance(raised.value.__cause__, OSError)
    assert snapshot.date_last_used is None
    assert list(tmp_path.glob(f"{source.name}_bck_*"))


def test_install_metadata_durability_failure_records_published_timestamp(tmp_path):
    """A post-rename flush error reports visible metadata and committed contents."""
    from pylizlib.core.os.snap import SnapshotInstallMetadataError
    from pylizlib.core.os.snap.storage.metadata import MetadataDurabilityError

    source, snapshot, manager = stored_snapshot(tmp_path)
    before = manager.path_snapshot_json.read_bytes()
    error = MetadataDurabilityError(manager.path_snapshot_json, OSError("directory fsync failed"))
    write_bytes = SnapshotSerializer.write_bytes

    def publish_then_fail(path, contents):
        """Persist the JSON, then simulate failure flushing its directory entry."""
        write_bytes(path, contents)
        if path == manager.path_snapshot_json:
            raise error

    with patch.object(SnapshotSerializer, "write_bytes", side_effect=publish_then_fail):
        with pytest.raises(SnapshotInstallMetadataError) as raised:
            manager.install()

    assert (source / "value.txt").read_text() == "stored"
    assert snapshot.date_last_used is not None
    assert raised.value.installation_completed is True
    assert raised.value.metadata_published is True
    assert raised.value.durability_confirmed is False
    stored = SnapshotSerializer.from_json(manager.path_snapshot_json)
    assert stored.date_last_used == snapshot.date_last_used
    assert manager.path_snapshot_json.read_bytes() != before
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


def test_edit_planner_keeps_storage_path_when_presentation_index_changes(tmp_path):
    """Changing an index does not create a stored-directory move."""
    from pylizlib.core.os.snap.operations.edits import SnapshotEditPlanner

    _, snapshot, manager = stored_snapshot(tmp_path)
    before = manager.path_snapshot_json.read_bytes()
    original_name = snapshot.directories[0].directory_name
    snapshot.directories[0].index = 2
    plan = SnapshotEditPlanner(manager._storage()).build([])
    assert plan.old_json == before
    assert plan.moves == []
    assert snapshot.directories[0].directory_name == original_name
    assert (manager.path_snapshot / original_name).is_dir()
    assert manager.path_snapshot_json.read_bytes() == before


def test_editor_restores_exact_metadata_bytes_when_save_partially_fails(tmp_path):
    """A failed JSON rewrite restores exact bytes without moving stable copies."""
    from pylizlib.core.os.snap.diff import get_edits_between_snapshots
    from pylizlib.core.os.snap.operations.edits import SnapshotEditor

    _, snapshot, manager = stored_snapshot(tmp_path)
    before = json.dumps(json.loads(manager.path_snapshot_json.read_text()), indent=2).encode()
    manager.path_snapshot_json.write_bytes(before)
    original = snapshot.clone()
    snapshot.directories[0].index = 2
    requested_name = snapshot.directories[0].directory_name

    write_bytes = SnapshotSerializer.write_bytes
    failed = False

    def fail_save(path, contents):
        """Simulate an interrupted active metadata publication after directory swaps."""
        nonlocal failed
        if path == manager.path_snapshot_json and not failed:
            failed = True
            assert (manager.path_snapshot / original.directories[0].directory_name).is_dir()
            assert (manager.path_snapshot / requested_name).is_dir()
            path.write_bytes(b"partial")
            raise OSError("save failed")
        return write_bytes(path, contents)

    with patch.object(SnapshotSerializer, "write_bytes", side_effect=fail_save):
        with pytest.raises(OSError, match="save failed"):
            SnapshotEditor(manager._storage()).apply(get_edits_between_snapshots(original, snapshot))
    assert manager.path_snapshot_json.read_bytes() == before
    assert (manager.path_snapshot / original.directories[0].directory_name).is_dir()
    assert requested_name == original.directories[0].directory_name
    assert snapshot.directories[0].index == original.directories[0].index


def test_editor_keeps_published_edit_when_metadata_durability_is_uncertain(tmp_path):
    """A published index edit retains its stable directory path."""
    from pylizlib.core.os.snap.diff import get_edits_between_snapshots
    from pylizlib.core.os.snap.operations.edits import SnapshotEditor
    from pylizlib.core.os.snap.storage.metadata import MetadataDurabilityError

    _, snapshot, manager = stored_snapshot(tmp_path)
    original = snapshot.clone()
    old_name = snapshot.directories[0].directory_name
    snapshot.directories[0].index = 2
    new_name = snapshot.directories[0].directory_name
    write_bytes = SnapshotSerializer.write_bytes
    error = MetadataDurabilityError(manager.path_snapshot_json, OSError("directory fsync failed"))

    def publish_then_fail(path, contents):
        """Publish the complete JSON, then report an uncertain directory flush."""
        write_bytes(path, contents)
        if path == manager.path_snapshot_json:
            raise error

    with patch.object(SnapshotSerializer, "write_bytes", side_effect=publish_then_fail):
        with pytest.raises(MetadataDurabilityError) as raised:
            SnapshotEditor(manager._storage()).apply(get_edits_between_snapshots(original, snapshot))

    assert raised.value.published is True
    assert old_name == new_name
    assert (manager.path_snapshot / old_name).is_dir()
    assert (manager.path_snapshot / new_name).is_dir()
    assert SnapshotSerializer.from_json(manager.path_snapshot_json).directories[0].directory_name == new_name
    assert snapshot.directories[0].directory_name == new_name
    workspaces = list((manager.path_snapshot / ".pyliz_transactions").iterdir())
    assert len(workspaces) == 1
    assert SnapshotSerializer.read_text(workspaces[0] / "journal.json")


def test_commit_decided_edit_recovery_preserves_a_directory_name_cycle(tmp_path):
    """Commit recovery does not confuse new entries with old source names."""
    from pylizlib.core.os.snap.diff import get_edits_between_snapshots
    from pylizlib.core.os.snap.storage.metadata import MetadataDurabilityError
    from pylizlib.core.os.snap.storage.transactions import recover_storage_transactions

    sources = []
    associations = []
    for index in range(1, 4):
        source = tmp_path / f"cycle-source-{index}"
        source.mkdir()
        (source / "identity.txt").write_text(f"copy-{index}")
        sources.append(source)
        associations.append(SnapDirAssociation(index, str(source), f"cycle-{index}"))
    snapshot = Snapshot("cycle-recovery", "cycle", "", directories=associations)
    manager = SnapshotManager(snapshot, tmp_path / "cycle-catalogue", SnapshotSettings())
    manager.create()
    original = snapshot.clone()
    for association, index in zip(snapshot.directories, (2, 3, 1)):
        association.index = index

    write_bytes = SnapshotSerializer.write_bytes
    error = MetadataDurabilityError(manager.path_snapshot_json, OSError("directory fsync failed"))

    def publish_then_fail(path, contents):
        """Publish cycle metadata, then leave the committed journal for restart."""
        write_bytes(path, contents)
        if path == manager.path_snapshot_json:
            raise error

    with patch.object(SnapshotSerializer, "write_bytes", side_effect=publish_then_fail):
        with pytest.raises(MetadataDurabilityError):
            manager.update_from_actions_list(get_edits_between_snapshots(original, snapshot))

    recover_storage_transactions(manager._storage())
    by_id = {association.folder_id: association for association in snapshot.directories}
    for index in range(1, 4):
        association = by_id[f"cycle-{index}"]
        assert (manager.path_snapshot / association.directory_name / "identity.txt").read_text() == f"copy-{index}"
    assert not (manager.path_snapshot / ".pyliz_transactions").exists()


def test_editor_retains_removed_directory_after_published_metadata_error(tmp_path):
    """A removed copy remains recoverable when published metadata cannot be flushed."""
    from pylizlib.core.os.snap.diff import get_edits_between_snapshots
    from pylizlib.core.os.snap.operations.edits import SnapshotEditor
    from pylizlib.core.os.snap.storage.metadata import MetadataDurabilityError

    _, snapshot, manager = stored_snapshot(tmp_path)
    original = snapshot.clone()
    removed_name = snapshot.directories[0].directory_name
    snapshot.directories.clear()
    write_bytes = SnapshotSerializer.write_bytes
    error = MetadataDurabilityError(manager.path_snapshot_json, OSError("directory fsync failed"))

    def publish_then_fail(path, contents):
        """Publish the removal, then report an uncertain directory flush."""
        write_bytes(path, contents)
        if path == manager.path_snapshot_json:
            raise error

    with patch.object(SnapshotSerializer, "write_bytes", side_effect=publish_then_fail):
        with pytest.raises(MetadataDurabilityError):
            SnapshotEditor(manager._storage()).apply(get_edits_between_snapshots(original, snapshot))

    assert SnapshotSerializer.from_json(manager.path_snapshot_json).directories == []
    assert snapshot.directories == []
    assert not (manager.path_snapshot / removed_name).exists()
    staged = list((manager.path_snapshot / ".pyliz_transactions").iterdir())
    assert len(staged) == 1
    assert (staged[0] / "original_0" / "value.txt").read_text() == "stored"


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
    """A failed prepared sync leaves active JSON and stored copies untouched."""
    from pylizlib.core.os.snap.operations.sync import SnapshotSynchronizer

    source, snapshot, manager = stored_snapshot(tmp_path)
    association = snapshot.directories[0]
    before = manager.path_snapshot_json.read_bytes()
    old_manifest = association.integrity_manifest
    old_size = association.mb_size
    old_date = snapshot.date_last_modified
    (source / "value.txt").write_text("new live contents with a different size")

    def fail_save(_snapshot, path):
        """Interrupt preparation of the new JSON before directory publication."""
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
    assert manager.path_snapshot_json.read_bytes() == before
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


def test_snapshot_tree_journal_finishes_publication_after_process_stops(tmp_path):
    """A crash after moving the old snapshot is completed from its journal."""
    source, _, manager = stored_snapshot(tmp_path, "crash-create")
    (manager.path_snapshot / "old-only.txt").write_text("old version")
    (source / "value.txt").write_text("new version")
    real_rename = Path.rename

    def stop_after_backup(source_path, target_path):
        """Stop after the old root reached its durable transaction backup."""
        source_path = Path(source_path)
        target_path = Path(target_path)
        if source_path == manager.path_snapshot and target_path.name == "original" and target_path.parent.parent.name == ".pyliz_transactions":
            real_rename(source_path, target_path)
            raise SystemExit("simulated process termination")
        return real_rename(source_path, target_path)

    with patch.object(Path, "rename", autospec=True, side_effect=stop_after_backup):
        with pytest.raises(SystemExit, match="simulated process termination"):
            manager.create(replace_existing=True)

    workspace = next((manager.path_catalogue / ".pyliz_transactions").iterdir())
    journal = json.loads((workspace / "journal.json").read_text())
    assert journal["state"] == "commit_decided"
    assert (workspace / "original" / "old-only.txt").read_text() == "old version"
    assert (workspace / "snapshot" / manager.snapshot.directories[0].directory_name / "value.txt").read_text() == "new version"
    assert not manager.path_snapshot.exists()

    catalogue = api.SnapshotCatalogue(manager.path_catalogue, manager.settings)
    loaded = catalogue.get_all()
    assert len(loaded) == 1
    assert (manager.path_snapshot / loaded[0].directories[0].directory_name / "value.txt").read_text() == "new version"
    assert not (manager.path_snapshot / "old-only.txt").exists()
    assert not (manager.path_catalogue / ".pyliz_transactions").exists()


def test_install_journal_restores_original_after_process_stops_mid_swap(tmp_path):
    """A prepared install journal restores a destination moved before a crash."""
    source, _, manager = stored_snapshot(tmp_path, "crash-install")
    (source / "value.txt").write_text("live version")
    real_rename = Path.rename

    def stop_after_backup(source_path, target_path):
        """Stop after the original destination has moved aside."""
        source_path = Path(source_path)
        target_path = Path(target_path)
        if source_path == source and target_path.parent == source.parent and target_path.name.startswith(f"{source.name}_bck_"):
            real_rename(source_path, target_path)
            raise SystemExit("simulated process termination")
        return real_rename(source_path, target_path)

    with patch.object(Path, "rename", autospec=True, side_effect=stop_after_backup):
        with pytest.raises(SystemExit, match="simulated process termination"):
            manager.install()

    workspaces = list((manager.path_snapshot / ".pyliz_transactions").iterdir())
    assert len(workspaces) == 1
    assert json.loads((workspaces[0] / "journal.json").read_text())["state"] == "prepared"
    assert not source.exists()
    assert next(source.parent.glob(f"{source.name}_bck_*"))

    from pylizlib.core.os.snap.storage.transactions import recover_storage_transactions

    recover_storage_transactions(manager._storage())
    assert (source / "value.txt").read_text() == "live version"
    assert list(source.parent.glob(f"{source.name}_bck_*")) == []
    assert list(source.parent.glob(f"{source.name}_staging_*")) == []
    assert not (manager.path_snapshot / ".pyliz_transactions").exists()


def test_unreadable_install_journal_preserves_both_recovery_copies(tmp_path):
    """An invalid journal stops recovery before deleting its backup or stage."""
    from pylizlib.core.os.snap.storage.transactions import TransactionRecoveryError, recover_storage_transactions

    source, _, manager = stored_snapshot(tmp_path, "crash-invalid-journal")
    (source / "value.txt").write_text("live version")
    real_rename = Path.rename

    def stop_after_backup(source_path, target_path):
        """Leave a prepared install journal after moving the live directory."""
        source_path = Path(source_path)
        target_path = Path(target_path)
        if source_path == source and target_path.name.startswith(f"{source.name}_bck_"):
            real_rename(source_path, target_path)
            raise SystemExit("simulated process termination")
        return real_rename(source_path, target_path)

    with patch.object(Path, "rename", autospec=True, side_effect=stop_after_backup):
        with pytest.raises(SystemExit):
            manager.install()

    workspace = next((manager.path_snapshot / ".pyliz_transactions").iterdir())
    backup = next(source.parent.glob(f"{source.name}_bck_*"))
    stage = next(source.parent.glob(f"{source.name}_staging_*"))
    (workspace / "journal.json").write_text("not valid JSON")
    with pytest.raises(TransactionRecoveryError, match="Could not recover transaction"):
        recover_storage_transactions(manager._storage())
    assert backup.is_dir()
    assert stage.is_dir()
    assert not source.exists()
    assert (workspace / "journal.json").read_text() == "not valid JSON"


def test_sync_journal_restores_stored_copy_after_process_stops_mid_swap(tmp_path):
    """A prepared sync journal restores its original stored copy after restart."""
    source, snapshot, manager = stored_snapshot(tmp_path, "crash-sync")
    association = snapshot.directories[0]
    stored_copy = manager.path_snapshot / association.directory_name
    (source / "value.txt").write_text("new live version")
    real_rename = Path.rename

    def stop_after_backup(source_path, target_path):
        """Stop after the previous stored copy has moved to its backup."""
        source_path = Path(source_path)
        target_path = Path(target_path)
        if source_path == stored_copy and target_path.parent == manager.path_snapshot and target_path.name.startswith(f"{stored_copy.name}_bck_"):
            real_rename(source_path, target_path)
            raise SystemExit("simulated process termination")
        return real_rename(source_path, target_path)

    with patch.object(Path, "rename", autospec=True, side_effect=stop_after_backup):
        with pytest.raises(SystemExit, match="simulated process termination"):
            manager.update_associated_dirs_from_system()

    workspaces = list((manager.path_snapshot / ".pyliz_transactions").iterdir())
    assert len(workspaces) == 1
    assert not stored_copy.exists()
    assert next(manager.path_snapshot.glob(f"{stored_copy.name}_bck_*"))

    from pylizlib.core.os.snap.storage.transactions import recover_storage_transactions

    recover_storage_transactions(manager._storage())
    assert (stored_copy / "value.txt").read_text() == "stored"
    assert list(manager.path_snapshot.glob(f"{stored_copy.name}_bck_*")) == []
    assert list(manager.path_snapshot.glob(f"{stored_copy.name}_staging_*")) == []
    assert not (manager.path_snapshot / ".pyliz_transactions").exists()


def test_edit_journal_restores_original_names_after_process_stops_during_staging(tmp_path):
    """A crash while moving old edit directories is recovered before reuse."""
    _, snapshot, manager = stored_snapshot(tmp_path, "crash-edit")
    before_json = manager.path_snapshot_json.read_bytes()
    old_name = snapshot.directories[0].directory_name
    old_directory = manager.path_snapshot / old_name
    real_rename = Path.rename

    def stop_after_staging_move(source_path, target_path):
        """Stop after the original association entered its journal workspace."""
        source_path = Path(source_path)
        target_path = Path(target_path)
        if source_path == old_directory and target_path.name == "original_0" and target_path.parent.parent.name == ".pyliz_transactions":
            real_rename(source_path, target_path)
            raise SystemExit("simulated process termination")
        return real_rename(source_path, target_path)

    snapshot.directories.clear()
    from pylizlib.core.os.snap.utils import SnapshotUtils

    actions = SnapshotUtils.get_edits_between_snapshots(SnapshotSerializer.from_json(manager.path_snapshot_json), snapshot)
    with patch.object(Path, "rename", autospec=True, side_effect=stop_after_staging_move):
        with pytest.raises(SystemExit, match="simulated process termination"):
            manager.update_from_actions_list(actions)

    workspace = next((manager.path_snapshot / ".pyliz_transactions").iterdir())
    assert json.loads((workspace / "journal.json").read_text())["state"] == "prepared"
    assert not old_directory.exists()

    from pylizlib.core.os.snap.storage.transactions import recover_storage_transactions

    recover_storage_transactions(manager._storage())
    assert (old_directory / "value.txt").read_text() == "stored"
    assert manager.path_snapshot_json.read_bytes() == before_json
    assert not (manager.path_snapshot / ".pyliz_transactions").exists()


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


def test_association_copy_service_cleans_partial_destination_on_strategy_failure(tmp_path):
    """Association storage keeps cleanup even for custom failing strategies."""
    from pylizlib.core.os.snap.copy_strategy import DirectoryCopyStrategy
    from pylizlib.core.os.snap.storage.association import copy_association

    class FailingStrategy(DirectoryCopyStrategy):
        """Create a partial destination then fail to exercise caller cleanup."""

        def copy_directory(self, source, destination, progress_callback=None, message_callback=None, *, manifest=None, expected_manifest=None):
            """Leave a deliberately incomplete directory for the association adapter."""
            destination.mkdir()
            (destination / "partial").write_text("partial")
            raise OSError("custom copy failed")

    source = tmp_path / "source"
    source.mkdir()
    association = SnapDirAssociation(1, str(source), "a")
    storage = tmp_path / "storage"
    with pytest.raises(OSError, match="custom copy failed"):
        copy_association(association, storage, copy_strategy=FailingStrategy())
    assert not (storage / association.directory_name).exists()


def test_association_factory_keeps_public_generator_and_global_index(tmp_path):
    """Factory extraction preserves the class-level index and path selection."""
    from pylizlib.core.os.snap.factories import gen_random_association_list

    choices = tmp_path / "choices"
    (choices / "only").mkdir(parents=True)
    with patch.object(SnapDirAssociation, "_current_index", 40):
        associations = gen_random_association_list(2, choices)
        assert [a.index for a in associations] == [41, 42]
        assert [a.original_path for a in associations] == [(choices / "only").as_posix()] * 2


def test_create_and_install_keep_distinct_scan_behavior_without_observer(tmp_path):
    """Create keeps its byte-scan adapter, while install passes no copy observer."""
    from pylizlib.core.os.snap.copy_strategy import SequentialFileCopyStrategy

    source = tmp_path / "source"
    source.mkdir()
    (source / "value").write_text("payload")
    snapshot = Snapshot("scan", "scan", "", directories=[SnapDirAssociation(1, str(source), "a")])
    strategy = SequentialFileCopyStrategy()
    manager = SnapshotManager(snapshot, tmp_path / "catalogue", SnapshotSettings(copy_strategy=strategy))
    with patch.object(strategy, "_total_bytes", wraps=strategy._total_bytes) as scan:
        manager.create()
        assert scan.call_count == 1
        manager.install()
        assert scan.call_count == 1


@pytest.mark.parametrize("callback_result,expected_count", [(False, 0), (0, 1), (None, 1)])
def test_search_only_requires_path_lookup_and_cancels_on_false_identity(tmp_path, callback_result, expected_count):
    """A path-only collaborator works; false-like values do not all cancel."""
    _, snapshot, manager = stored_snapshot(tmp_path)

    class PathsOnly:
        """Minimal structural implementation with no catalogue CRUD methods."""

        def get_snap_directory_path(self, snap):
            """Return the one stored snapshot root used by this test."""
            assert snap is snapshot
            return manager.path_snapshot

    results = api.SnapshotSearcher(PathsOnly()).search(
        snapshot,
        api.SnapshotSearchParams("stored"),
        lambda *_: callback_result,
    )
    assert len(results) == expected_count


def test_search_matching_keeps_query_case_and_normalizes_extensions(tmp_path):
    """Search queries remain case-sensitive while extension filters do not."""
    _, snapshot, manager = stored_snapshot(tmp_path)
    searcher = api.SnapshotSearcher(api.SnapshotCatalogue(manager.path_catalogue))
    assert searcher.search(snapshot, api.SnapshotSearchParams("STORED")) == []
    result = searcher.search(snapshot, api.SnapshotSearchParams("stored", extensions=[".TXT"]))
    assert len(result) == 1
    assert result[0].line_content == "stored"
    params = api.SnapshotSearchParams("VALUE", search_target=api.SearchTarget.FILE_NAME)
    assert searcher.search(snapshot, params) == []


def test_default_settings_still_share_identity_per_public_constructor(tmp_path):
    """The refactor deliberately retains the legacy shared-default behavior."""
    snapshot = Snapshot("defaults", "defaults", "")
    first = SnapshotManager(snapshot, tmp_path / "catalogue")
    second = SnapshotManager(snapshot, tmp_path / "catalogue")
    assert first.settings is second.settings is SnapshotManager.__init__.__defaults__[0]
    first_catalogue = api.SnapshotCatalogue(tmp_path / "catalogue")
    second_catalogue = api.SnapshotCatalogue(tmp_path / "catalogue")
    assert first_catalogue.settings is second_catalogue.settings is api.SnapshotCatalogue.__init__.__defaults__[0]
    assert first.settings is not first_catalogue.settings
