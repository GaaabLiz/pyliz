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
        id=snapshot_id, name=snapshot_id, desc="",
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
        [first, second], api.SnapshotSearchParams("stored"), cancel,
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
        "name", "desc", "author", "tags", "date_modified", "data", "date_last_modified",
    ]
