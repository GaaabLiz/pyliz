"""
Comprehensive test suite for pylizlib.core.os.snap

Covers every class, method, property and edge-case scenario.
Also validates bug-fixes applied to the module:
  - BUG-1  Mutable default datetime.now() in Snapshot and SnapEditAction
  - BUG-2  SnapshotManager.duplicate() mutated self.snapshot instead of a clone
  - BUG-3  SnapshotSerializer.from_json() referenced a non-existing field
            "date_last_installed" instead of "date_last_used"

Real image files are downloaded with SampleImageDownloader and placed under
TEST_LOCAL_ROOT so that snapshots contain actual binary content.
"""

import shutil
import time
import unittest
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from pylizlib.core.data.gen import gen_random_string
from pylizlib.core.os.snap import (
    BackupType,
    QueryType,
    SearchTarget,
    SnapDirAssociation,
    SnapEditAction,
    SnapEditType,
    Snapshot,
    SnapshotCatalogue,
    SnapshotManager,
    SnapshotSearcher,
    SnapshotSearchParams,
    SnapshotSerializer,
    SnapshotSettings,
    SnapshotSortKey,
    SnapshotUtils,
)
from pylizlib.core.testing.sample_downloader import SampleImageDownloader

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
TEST_ROOT = Path(__file__).parent.parent.parent
TEST_LOCAL_ROOT = TEST_ROOT.parent / "test_local" / "snap_tests"
CATALOGUE_PATH = TEST_LOCAL_ROOT / "catalogue"
SOURCE_DATA_PATH = TEST_LOCAL_ROOT / "source_data"
INSTALL_DEST_PATH = TEST_LOCAL_ROOT / "install_dest"
BACKUP_PATH = TEST_LOCAL_ROOT / "backups"

# Shared image cache so network is hit only once per test session
_IMAGE_CACHE = TEST_ROOT.parent / "test_local" / "_img_cache"
_downloader = SampleImageDownloader(cache_dir=_IMAGE_CACHE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reset_index():
    SnapDirAssociation._current_index = 0


def _create_source_dirs(base: Path, names: list, with_images: bool = False) -> list:
    """Creates source directories, optionally with downloaded images."""
    dirs = []
    for name in names:
        d = base / name
        d.mkdir(parents=True, exist_ok=True)
        if with_images:
            _downloader.download_images_to_folder(d, count=2, seeds=[f"{name}_a", f"{name}_b"])
        else:
            (d / f"{name}_file.txt").write_text(f"content of {name}", encoding="utf-8")
        dirs.append(d)
    return dirs


def _make_snapshot(name: str, source_dirs: list, n: int = 2) -> Snapshot:
    """Helper: builds a Snapshot from the first *n* source directories."""
    _reset_index()
    dirs = []
    for d in source_dirs[:n]:
        dirs.append(
            SnapDirAssociation(
                index=SnapDirAssociation.next_index(),
                original_path=str(d),
                folder_id=gen_random_string(6),
            )
        )
    return Snapshot(
        id=gen_random_string(10),
        name=name,
        desc=f"Description for {name}",
        author="TestSuite",
        directories=dirs,
        tags=["test"],
    )


# ===========================================================================
# TestSnapDirAssociationTestCase
# ===========================================================================

class TestSnapDirAssociationTestCase(unittest.TestCase):
    def setUp(self):
        TEST_LOCAL_ROOT.mkdir(parents=True, exist_ok=True)
        SOURCE_DATA_PATH.mkdir(parents=True, exist_ok=True)
        _reset_index()

    def tearDown(self):
        shutil.rmtree(TEST_LOCAL_ROOT, ignore_errors=True)

    def test_directory_name_format(self):
        d = SOURCE_DATA_PATH / "mydir"
        d.mkdir()
        assoc = SnapDirAssociation(index=5, original_path=str(d), folder_id="abc")
        self.assertEqual(assoc.directory_name, "5-mydir")

    def test_original_path_normalized_to_posix(self):
        d = SOURCE_DATA_PATH / "normdir"
        d.mkdir()
        assoc = SnapDirAssociation(index=1, original_path=str(d), folder_id="x")
        self.assertEqual(assoc.original_path, d.as_posix())

    def test_mb_size_calculated_when_none(self):
        d = SOURCE_DATA_PATH / "sizeddir"
        d.mkdir()
        (d / "bigfile.txt").write_text("x" * 10_000, encoding="utf-8")
        assoc = SnapDirAssociation(index=1, original_path=str(d), folder_id="sz")
        self.assertIsNotNone(assoc.mb_size)
        self.assertGreater(assoc.mb_size, 0.0)

    def test_mb_size_zero_when_dir_missing(self):
        assoc = SnapDirAssociation(
            index=1,
            original_path=str(SOURCE_DATA_PATH / "ghost_dir"),
            folder_id="g",
        )
        self.assertEqual(assoc.mb_size, 0.0)

    def test_mb_size_preserved_when_provided(self):
        d = SOURCE_DATA_PATH / "preserved"
        d.mkdir()
        assoc = SnapDirAssociation(index=1, original_path=str(d), folder_id="p", mb_size=42.0)
        self.assertEqual(assoc.mb_size, 42.0)

    def test_next_index_increments(self):
        _reset_index()
        i1 = SnapDirAssociation.next_index()
        i2 = SnapDirAssociation.next_index()
        self.assertEqual(i2, i1 + 1)

    def test_copy_install_to(self):
        src = SOURCE_DATA_PATH / "copydir"
        src.mkdir()
        (src / "a.txt").write_text("hello")
        sub = src / "subdir"
        sub.mkdir()
        (sub / "b.txt").write_text("world")

        target = TEST_LOCAL_ROOT / "target"
        assoc = SnapDirAssociation(index=1, original_path=str(src), folder_id="cp")
        assoc.copy_install_to(target)

        dest_dir = target / assoc.directory_name
        self.assertTrue(dest_dir.exists())
        self.assertTrue((dest_dir / "a.txt").exists())
        self.assertTrue((dest_dir / "subdir" / "b.txt").exists())

    def test_gen_random_returns_instance(self):
        (SOURCE_DATA_PATH / "rnd1").mkdir(exist_ok=True)
        (SOURCE_DATA_PATH / "rnd2").mkdir(exist_ok=True)
        assoc = SnapDirAssociation.gen_random(SOURCE_DATA_PATH, folder_id_length=4)
        self.assertIsInstance(assoc, SnapDirAssociation)
        self.assertEqual(len(assoc.folder_id), 4)

    def test_gen_random_list(self):
        for i in range(5):
            (SOURCE_DATA_PATH / f"rl{i}").mkdir(exist_ok=True)
        result = SnapDirAssociation.gen_random_list(3, SOURCE_DATA_PATH)
        self.assertEqual(len(result), 3)
        self.assertTrue(all(isinstance(a, SnapDirAssociation) for a in result))


# ===========================================================================
# TestSnapshotTestCase
# ===========================================================================

class TestSnapshotTestCase(unittest.TestCase):
    def setUp(self):
        TEST_LOCAL_ROOT.mkdir(parents=True, exist_ok=True)
        SOURCE_DATA_PATH.mkdir(parents=True, exist_ok=True)
        _create_source_dirs(SOURCE_DATA_PATH, ["d1", "d2", "d3"])

    def tearDown(self):
        shutil.rmtree(TEST_LOCAL_ROOT, ignore_errors=True)

    def test_bug1_date_created_unique_per_instance(self):
        """BUG-1: Each Snapshot instance must have its own date_created."""
        s1 = Snapshot(id="a", name="A", desc="")
        time.sleep(0.01)
        s2 = Snapshot(id="b", name="B", desc="")
        self.assertLessEqual(s1.date_created, s2.date_created)
        self.assertIsNot(s1.date_created, s2.date_created)

    def test_bug1_snap_edit_action_timestamp_unique(self):
        """BUG-1: SnapEditAction.timestamp must not be a shared default."""
        e1 = SnapEditAction(action_type=SnapEditType.ADD_DIR)
        time.sleep(0.01)
        e2 = SnapEditAction(action_type=SnapEditType.ADD_DIR)
        self.assertLessEqual(e1.timestamp, e2.timestamp)
        self.assertIsNot(e1.timestamp, e2.timestamp)

    def test_folder_name_equals_id(self):
        snap = Snapshot(id="snap_id_123", name="X", desc="")
        self.assertEqual(snap.folder_name, "snap_id_123")

    def test_tags_as_string_sorted(self):
        snap = Snapshot(id="1", name="T", desc="", tags=["gamma", "alpha", "beta"])
        self.assertEqual(snap.tags_as_string, "alpha, beta, gamma")

    def test_tags_as_string_empty(self):
        snap = Snapshot(id="2", name="T", desc="", tags=[])
        self.assertEqual(snap.tags_as_string, " ")

    def test_tags_as_string_single(self):
        snap = Snapshot(id="3", name="T", desc="", tags=["solo"])
        self.assertEqual(snap.tags_as_string, "solo")

    def test_data_add_get_has_edit_remove(self):
        snap = Snapshot(id="1", name="T", desc="")
        self.assertFalse(snap.has_data_item("key"))

        snap.add_data_item("key", "val1")
        self.assertTrue(snap.has_data_item("key"))
        self.assertEqual(snap.get_data_item("key"), "val1")

        snap.edit_data_item("key", "val2")
        self.assertEqual(snap.get_data_item("key"), "val2")

        with self.assertRaises(KeyError):
            snap.edit_data_item("nonexistent", "x")

        removed = snap.remove_data_item("key")
        self.assertEqual(removed, "val2")
        self.assertFalse(snap.has_data_item("key"))
        self.assertIsNone(snap.remove_data_item("key"))

    def test_data_clear_all(self):
        snap = Snapshot(id="1", name="T", desc="")
        snap.add_data_item("a", "1")
        snap.add_data_item("b", "2")
        snap.clear_all_data()
        self.assertEqual(len(snap.data), 0)

    def test_get_data_item_default(self):
        snap = Snapshot(id="1", name="T", desc="")
        self.assertEqual(snap.get_data_item("missing", default="default_val"), "default_val")
        self.assertEqual(snap.get_data_item("missing"), "")

    def test_get_for_table_array(self):
        snap = Snapshot(id="1", name="MyName", desc="MyDesc", tags=["b", "a"])
        snap.add_data_item("env", "production")
        snap.add_data_item("version", "1.0")
        row = snap.get_for_table_array(["env", "version", "missing"])
        self.assertEqual(row[0], "MyName")
        self.assertEqual(row[1], "MyDesc")
        self.assertEqual(row[2], "production")
        self.assertEqual(row[3], "1.0")
        self.assertEqual(row[4], "")
        self.assertRegex(row[5], r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}")
        self.assertEqual(row[6], "a, b")

    def test_get_assoc_dir_mb_size(self):
        src = _create_source_dirs(SOURCE_DATA_PATH, ["sz1", "sz2"])
        snap = _make_snapshot("SizeSnap", src, n=2)
        total = snap.get_assoc_dir_mb_size
        self.assertGreaterEqual(total, 0.0)
        self.assertEqual(total, sum(d.mb_size for d in snap.directories if d.mb_size is not None))

    def test_clone_is_deep_copy(self):
        src = _create_source_dirs(SOURCE_DATA_PATH, ["cl1"])
        snap1 = _make_snapshot("Original", src, n=1)
        snap1.add_data_item("key", "value")
        snap1.tags.append("extra")

        snap2 = snap1.clone()

        self.assertIsNot(snap1, snap2)
        self.assertEqual(snap1.id, snap2.id)

        snap2.id = "changed-id"
        snap2.name = "Changed"
        snap2.tags.append("new_tag")
        snap2.data["key"] = "new_value"
        snap2.directories.clear()

        self.assertNotEqual(snap1.id, snap2.id)
        self.assertNotEqual(snap1.name, snap2.name)
        self.assertNotIn("new_tag", snap1.tags)
        self.assertEqual(snap1.data["key"], "value")
        self.assertEqual(len(snap1.directories), 1)


# ===========================================================================
# TestSnapshotSettingsTestCase
# ===========================================================================

class TestSnapshotSettingsTestCase(unittest.TestCase):
    def test_defaults(self):
        s = SnapshotSettings()
        self.assertEqual(s.json_filename, "snapshot.json")
        self.assertIsNone(s.backup_path)
        self.assertFalse(s.backup_pre_install)
        self.assertFalse(s.backup_pre_modify)
        self.assertFalse(s.backup_pre_delete)
        self.assertTrue(s.install_with_everyone_full_control)
        self.assertEqual(s.snap_id_length, 20)
        self.assertEqual(s.folder_id_length, 6)

    def test_bck_enabled_only_when_path_and_flag_set(self):
        self.assertFalse(SnapshotSettings(backup_pre_install=True, backup_path=None).bck_before_install_enabled)
        self.assertFalse(SnapshotSettings(backup_pre_install=False, backup_path=Path("/tmp")).bck_before_install_enabled)
        self.assertTrue(SnapshotSettings(backup_pre_install=True, backup_path=Path("/tmp")).bck_before_install_enabled)
        self.assertTrue(SnapshotSettings(backup_pre_modify=True, backup_path=Path("/tmp")).bck_before_modify_enabled)
        self.assertTrue(SnapshotSettings(backup_pre_delete=True, backup_path=Path("/tmp")).bck_before_delete_enabled)


# ===========================================================================
# TestSnapshotSerializerTestCase
# ===========================================================================

class TestSnapshotSerializerTestCase(unittest.TestCase):
    def setUp(self):
        TEST_LOCAL_ROOT.mkdir(parents=True, exist_ok=True)
        SOURCE_DATA_PATH.mkdir(parents=True, exist_ok=True)
        _create_source_dirs(SOURCE_DATA_PATH, ["ser1", "ser2"])

    def tearDown(self):
        shutil.rmtree(TEST_LOCAL_ROOT, ignore_errors=True)

    def test_roundtrip(self):
        src = list(SOURCE_DATA_PATH.iterdir())
        snap = _make_snapshot("SerSnap", src, n=2)
        snap.add_data_item("k", "v")
        snap.tags = ["alpha", "beta"]
        snap.date_modified = datetime.now()

        json_path = TEST_LOCAL_ROOT / "ser_snap.json"
        SnapshotSerializer.to_json(snap, json_path)
        loaded = SnapshotSerializer.from_json(json_path)

        self.assertEqual(loaded.id, snap.id)
        self.assertEqual(loaded.name, snap.name)
        self.assertEqual(loaded.tags, snap.tags)
        self.assertEqual(loaded.data, snap.data)
        self.assertEqual(len(loaded.directories), len(snap.directories))
        self.assertIsNotNone(loaded.date_modified)

    def test_from_json_null_optionals(self):
        src = list(SOURCE_DATA_PATH.iterdir())
        snap = _make_snapshot("NullDates", src, n=1)
        json_path = TEST_LOCAL_ROOT / "null_dates.json"
        SnapshotSerializer.to_json(snap, json_path)
        loaded = SnapshotSerializer.from_json(json_path)
        self.assertIsNone(loaded.date_modified)
        self.assertIsNone(loaded.date_last_used)
        self.assertIsNone(loaded.date_last_modified)

    def test_bug3_date_last_used_survives_roundtrip(self):
        """BUG-3 fix: date_last_used must round-trip correctly through JSON."""
        src = list(SOURCE_DATA_PATH.iterdir())
        snap = _make_snapshot("Bug3Snap", src, n=1)
        snap.date_last_used = datetime(2025, 6, 15, 12, 0, 0)

        json_path = TEST_LOCAL_ROOT / "bug3.json"
        SnapshotSerializer.to_json(snap, json_path)
        loaded = SnapshotSerializer.from_json(json_path)

        self.assertIsNotNone(loaded.date_last_used)
        self.assertEqual(loaded.date_last_used, snap.date_last_used)

    def test_update_field_string(self):
        src = list(SOURCE_DATA_PATH.iterdir())
        snap = _make_snapshot("UpdateField", src, n=1)
        json_path = TEST_LOCAL_ROOT / "upd.json"
        SnapshotSerializer.to_json(snap, json_path)

        SnapshotSerializer.update_field(json_path, "name", "Updated Name")
        loaded = SnapshotSerializer.from_json(json_path)
        self.assertEqual(loaded.name, "Updated Name")

    def test_update_field_datetime(self):
        src = list(SOURCE_DATA_PATH.iterdir())
        snap = _make_snapshot("UpdDate", src, n=1)
        json_path = TEST_LOCAL_ROOT / "upd_date.json"
        SnapshotSerializer.to_json(snap, json_path)

        new_ts = datetime(2026, 1, 1, 0, 0, 0)
        SnapshotSerializer.update_field(json_path, "date_last_used", new_ts.isoformat())
        loaded = SnapshotSerializer.from_json(json_path)
        self.assertEqual(loaded.date_last_used, new_ts)


# ===========================================================================
# TestSnapshotUtilsTestCase
# ===========================================================================

class TestSnapshotUtilsTestCase(unittest.TestCase):
    def setUp(self):
        CATALOGUE_PATH.mkdir(parents=True, exist_ok=True)
        SOURCE_DATA_PATH.mkdir(parents=True, exist_ok=True)
        _create_source_dirs(SOURCE_DATA_PATH, ["u1", "u2", "u3"])

    def tearDown(self):
        shutil.rmtree(TEST_LOCAL_ROOT, ignore_errors=True)

    def test_get_snapshot_path(self):
        p = SnapshotUtils.get_snapshot_path("myid", CATALOGUE_PATH)
        self.assertEqual(p, CATALOGUE_PATH / "myid")

    def test_get_snapshot_json_path(self):
        p = SnapshotUtils.get_snapshot_json_path("myid", CATALOGUE_PATH, "snap.json")
        self.assertEqual(p, CATALOGUE_PATH / "myid" / "snap.json")

    def test_get_snapshot_from_path_raises_on_file(self):
        f = TEST_LOCAL_ROOT / "a_file.txt"
        f.write_text("x")
        with self.assertRaises(ValueError):
            SnapshotUtils.get_snapshot_from_path(f, "snapshot.json")

    def test_get_snapshot_from_path_raises_on_missing_dir(self):
        with self.assertRaises(FileNotFoundError):
            SnapshotUtils.get_snapshot_from_path(TEST_LOCAL_ROOT / "ghost", "snapshot.json")

    def test_get_snapshot_from_path_raises_on_missing_json(self):
        empty_dir = TEST_LOCAL_ROOT / "empty_snap"
        empty_dir.mkdir()
        with self.assertRaises(FileNotFoundError):
            SnapshotUtils.get_snapshot_from_path(empty_dir, "snapshot.json")

    def test_get_snapshot_from_path_success(self):
        src_dirs = list(p for p in SOURCE_DATA_PATH.iterdir() if p.is_dir())
        snap = _make_snapshot("UtilsSnap", src_dirs, n=1)
        snap_dir = CATALOGUE_PATH / snap.id
        snap_dir.mkdir()
        SnapshotSerializer.to_json(snap, snap_dir / "snapshot.json")

        loaded = SnapshotUtils.get_snapshot_from_path(snap_dir, "snapshot.json")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.id, snap.id)

    def test_gen_random_snap(self):
        snap = SnapshotUtils.gen_random_snap(SOURCE_DATA_PATH, id_length=8)
        self.assertIsInstance(snap, Snapshot)
        self.assertEqual(len(snap.id), 8)
        self.assertEqual(len(snap.directories), 3)

    def test_get_edits_no_change(self):
        src = list(p for p in SOURCE_DATA_PATH.iterdir() if p.is_dir())
        old = _make_snapshot("Old", src, n=2)
        new = old.clone()
        self.assertEqual(SnapshotUtils.get_edits_between_snapshots(old, new), [])

    def test_get_edits_add(self):
        src = sorted(p for p in SOURCE_DATA_PATH.iterdir() if p.is_dir())
        old = _make_snapshot("Old", src, n=2)
        new = old.clone()
        new.directories.append(SnapDirAssociation(index=99, original_path=str(src[2]), folder_id="NEW"))
        edits = SnapshotUtils.get_edits_between_snapshots(old, new)
        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0].action_type, SnapEditType.ADD_DIR)

    def test_get_edits_remove(self):
        src = sorted(p for p in SOURCE_DATA_PATH.iterdir() if p.is_dir())
        old = _make_snapshot("Old", src, n=2)
        new = old.clone()
        removed = new.directories.pop(0)
        edits = SnapshotUtils.get_edits_between_snapshots(old, new)
        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0].action_type, SnapEditType.REMOVE_DIR)
        self.assertEqual(edits[0].folder_id_to_remove, removed.folder_id)

    def test_get_edits_add_and_remove(self):
        src = sorted(p for p in SOURCE_DATA_PATH.iterdir() if p.is_dir())
        old = _make_snapshot("Old", src, n=2)
        new = old.clone()
        new.directories.pop(0)
        new.directories.append(SnapDirAssociation(index=99, original_path=str(src[2]), folder_id="NEW2"))
        edits = SnapshotUtils.get_edits_between_snapshots(old, new)
        self.assertEqual(len(edits), 2)
        types = {e.action_type for e in edits}
        self.assertIn(SnapEditType.ADD_DIR, types)
        self.assertIn(SnapEditType.REMOVE_DIR, types)

    def test_sort_by_name_asc(self):
        now = datetime.now()
        s1 = Snapshot(id="1", name="Gamma", desc="", date_created=now)
        s2 = Snapshot(id="2", name="alpha", desc="", date_created=now)
        s3 = Snapshot(id="3", name="Beta", desc="", date_created=now)
        result = SnapshotUtils.sort_snapshots([s1, s2, s3], SnapshotSortKey.NAME)
        self.assertEqual([s.name for s in result], ["alpha", "Beta", "Gamma"])

    def test_sort_by_name_desc(self):
        now = datetime.now()
        s1 = Snapshot(id="1", name="Gamma", desc="", date_created=now)
        s2 = Snapshot(id="2", name="alpha", desc="", date_created=now)
        result = SnapshotUtils.sort_snapshots([s1, s2], SnapshotSortKey.NAME, reverse=True)
        self.assertEqual([s.name for s in result], ["Gamma", "alpha"])

    def test_sort_none_at_end(self):
        now = datetime.now()
        s1 = Snapshot(id="1", name="A", desc="", date_modified=now)
        s2 = Snapshot(id="2", name="B", desc="", date_modified=None)
        s3 = Snapshot(id="3", name="C", desc="", date_modified=now - timedelta(days=1))
        result = SnapshotUtils.sort_snapshots([s1, s2, s3], SnapshotSortKey.DATE_MODIFIED)
        self.assertEqual(result[-1].id, "2")
        self.assertEqual(result[0].id, "3")

    def test_sort_by_assoc_dir_mb_size(self):
        src = sorted(p for p in SOURCE_DATA_PATH.iterdir() if p.is_dir())
        (src[0] / "small.txt").write_text("x" * 100)
        (src[1] / "medium.txt").write_text("x" * 5_000)
        (src[2] / "large.txt").write_text("x" * 100_000)

        snap_s = _make_snapshot("Small", [src[0]], n=1)
        snap_m = _make_snapshot("Medium", [src[1]], n=1)
        snap_l = _make_snapshot("Large", [src[2]], n=1)

        sorted_asc = SnapshotUtils.sort_snapshots([snap_l, snap_m, snap_s], SnapshotSortKey.ASSOC_DIR_MB_SIZE)
        self.assertEqual([s.name for s in sorted_asc], ["Small", "Medium", "Large"])


# ===========================================================================
# TestSnapshotManagerTestCase
# ===========================================================================

class TestSnapshotManagerTestCase(unittest.TestCase):
    def setUp(self):
        CATALOGUE_PATH.mkdir(parents=True, exist_ok=True)
        SOURCE_DATA_PATH.mkdir(parents=True, exist_ok=True)
        self._src = _create_source_dirs(SOURCE_DATA_PATH, ["m1", "m2", "m3"])

    def tearDown(self):
        shutil.rmtree(TEST_LOCAL_ROOT, ignore_errors=True)

    def _manager(self, snap, settings=None):
        return SnapshotManager(snap, CATALOGUE_PATH, settings or SnapshotSettings())

    def test_create_builds_directory_and_json(self):
        snap = _make_snapshot("MgrCreate", self._src, n=2)
        mgr = self._manager(snap)
        self.assertFalse(mgr.path_snapshot.exists())
        mgr.create()
        self.assertTrue(mgr.path_snapshot.exists())
        self.assertTrue(mgr.path_snapshot_json.exists())
        for assoc in snap.directories:
            self.assertTrue((mgr.path_snapshot / assoc.directory_name).exists())

    def test_create_clears_existing_contents(self):
        snap = _make_snapshot("MgrRecreate", self._src, n=1)
        mgr = self._manager(snap)
        mgr.create()
        leftover = mgr.path_snapshot / "leftover.txt"
        leftover.write_text("stale")
        mgr.create()
        self.assertFalse(leftover.exists())

    def test_delete_removes_directory(self):
        snap = _make_snapshot("MgrDel", self._src, n=1)
        mgr = self._manager(snap)
        mgr.create()
        mgr.delete()
        self.assertFalse(mgr.path_snapshot.exists())

    def test_delete_nonexistent_does_not_raise(self):
        snap = _make_snapshot("MgrDelNone", self._src, n=1)
        mgr = self._manager(snap)
        mgr.delete()  # should not raise

    def test_update_json_base_fields(self):
        snap = _make_snapshot("BaseFields", self._src, n=1)
        mgr = self._manager(snap)
        mgr.create()
        snap.name = "Renamed"
        snap.desc = "New desc"
        snap.author = "NewAuthor"
        snap.tags = ["t1", "t2"]
        mgr.update_json_base_fields()
        loaded = SnapshotSerializer.from_json(mgr.path_snapshot_json)
        self.assertEqual(loaded.name, "Renamed")
        self.assertEqual(loaded.desc, "New desc")
        self.assertEqual(loaded.author, "NewAuthor")
        self.assertEqual(loaded.tags, ["t1", "t2"])
        self.assertIsNotNone(loaded.date_modified)

    def test_update_json_data_fields(self):
        snap = _make_snapshot("DataFields", self._src, n=1)
        mgr = self._manager(snap)
        mgr.create()
        snap.data["env"] = "prod"
        mgr.update_json_data_fields()
        loaded = SnapshotSerializer.from_json(mgr.path_snapshot_json)
        self.assertEqual(loaded.data.get("env"), "prod")
        self.assertIsNotNone(loaded.date_last_modified)

    def test_install_directory_and_uninstall(self):
        snap = _make_snapshot("InstDir", self._src, n=1)
        mgr = self._manager(snap)
        mgr.create()

        new_dir = SOURCE_DATA_PATH / "new_install_dir"
        new_dir.mkdir()
        (new_dir / "new.txt").write_text("new content")

        mgr.install_directory(new_dir)
        self.assertEqual(len(snap.directories), 2)
        added_assoc = snap.directories[-1]
        self.assertTrue((mgr.path_snapshot / added_assoc.directory_name).exists())

        mgr.uninstall_directory_by_folder_id(added_assoc.folder_id)
        self.assertEqual(len(snap.directories), 1)
        self.assertFalse((mgr.path_snapshot / added_assoc.directory_name).exists())

    def test_install_directory_raises_on_invalid_path(self):
        snap = _make_snapshot("InstDirBad", self._src, n=1)
        mgr = self._manager(snap)
        mgr.create()
        with self.assertRaises(ValueError):
            mgr.install_directory(SOURCE_DATA_PATH / "does_not_exist")

    def test_uninstall_nonexistent_folder_id_is_noop(self):
        snap = _make_snapshot("UninstNoOp", self._src, n=1)
        mgr = self._manager(snap)
        mgr.create()
        initial_count = len(snap.directories)
        mgr.uninstall_directory_by_folder_id("nonexistent_id")
        self.assertEqual(len(snap.directories), initial_count)

    def test_bug2_duplicate_does_not_mutate_original(self):
        """BUG-2: duplicate() must NOT change self.snapshot.id or .name."""
        snap = _make_snapshot("DupOriginal", self._src, n=1)
        mgr = self._manager(snap)
        mgr.create()
        original_id = snap.id
        original_name = snap.name
        mgr.duplicate()
        self.assertEqual(snap.id, original_id, "BUG-2: duplicate() mutated original snapshot ID")
        self.assertEqual(snap.name, original_name, "BUG-2: duplicate() mutated original snapshot name")

    def test_duplicate_creates_new_snapshot_on_disk(self):
        snap = _make_snapshot("DupSource", self._src, n=1)
        mgr = self._manager(snap)
        mgr.create()
        mgr.duplicate()

        self.assertTrue(mgr.path_snapshot.exists())
        all_dirs = [d for d in CATALOGUE_PATH.iterdir() if d.is_dir()]
        self.assertEqual(len(all_dirs), 2)
        new_dir = next(d for d in all_dirs if d.name != snap.id)
        loaded = SnapshotSerializer.from_json(new_dir / SnapshotSettings().json_filename)
        self.assertIn("Copy", loaded.name)
        self.assertNotEqual(loaded.id, snap.id)

    def test_duplicate_raises_on_missing_path(self):
        snap = _make_snapshot("DupMissing", self._src, n=1)
        mgr = self._manager(snap)
        with self.assertRaises(FileNotFoundError):
            mgr.duplicate()

    def test_update_associated_dirs_from_system(self):
        snap = _make_snapshot("UpdateAssoc", self._src, n=1)
        mgr = self._manager(snap)
        mgr.create()
        original_dir = Path(snap.directories[0].original_path)
        (original_dir / "new_file.txt").write_text("added after create")
        mgr.update_associated_dirs_from_system()
        internal_copy = mgr.path_snapshot / snap.directories[0].directory_name
        self.assertTrue((internal_copy / "new_file.txt").exists())
        loaded = SnapshotSerializer.from_json(mgr.path_snapshot_json)
        self.assertIsNotNone(loaded.date_last_modified)

    def test_update_associated_dirs_missing_source_sets_size_zero(self):
        snap = _make_snapshot("AssocMissing", self._src, n=1)
        mgr = self._manager(snap)
        mgr.create()
        original_dir = Path(snap.directories[0].original_path)
        shutil.rmtree(original_dir)
        with self.assertLogs(level="WARNING"):
            mgr.update_associated_dirs_from_system()
        loaded = SnapshotSerializer.from_json(mgr.path_snapshot_json)
        self.assertEqual(loaded.directories[0].mb_size, 0.0)

    def test_install_copies_content_to_original_path(self):
        snap = _make_snapshot("MgrInstall", self._src, n=1)
        mgr = self._manager(snap)
        mgr.create()
        original_dir = Path(snap.directories[0].original_path)
        (original_dir / "extra.txt").write_text("should be removed")
        mgr.install()
        self.assertFalse((original_dir / "extra.txt").exists())
        self.assertTrue((original_dir / "m1_file.txt").exists())

    def test_install_updates_date_last_used(self):
        snap = _make_snapshot("MgrInstallDate", self._src, n=1)
        mgr = self._manager(snap)
        mgr.create()
        mgr.install()
        loaded = SnapshotSerializer.from_json(mgr.path_snapshot_json)
        self.assertIsNotNone(loaded.date_last_used)

    def test_remove_installed_copies(self):
        install_dir = TEST_LOCAL_ROOT / "installed_copy"
        install_dir.mkdir(parents=True)
        (install_dir / "a.txt").write_text("x")
        _reset_index()
        snap = Snapshot(
            id=gen_random_string(8), name="RemoveSnap", desc="",
            directories=[SnapDirAssociation(index=1, original_path=str(install_dir), folder_id="rem1")],
        )
        mgr = self._manager(snap)
        self.assertTrue(install_dir.exists())
        mgr.remove_installed_copies()
        self.assertFalse(install_dir.exists())

    def test_create_backup_snapshot_directory(self):
        snap = _make_snapshot("BckSnap", self._src, n=1)
        mgr = self._manager(snap)
        mgr.create()
        BACKUP_PATH.mkdir(parents=True, exist_ok=True)
        mgr.create_backup(BACKUP_PATH, "test_prefix", BackupType.SNAPSHOT_DIRECTORY)
        zips = list(BACKUP_PATH.glob("*.zip"))
        self.assertEqual(len(zips), 1)
        self.assertIn("test_prefix", zips[0].name)

    def test_create_backup_associated_directories(self):
        snap = _make_snapshot("BckAssoc", self._src, n=1)
        mgr = self._manager(snap)
        mgr.create()
        BACKUP_PATH.mkdir(parents=True, exist_ok=True)
        mgr.create_backup(BACKUP_PATH, "assoc_bck", BackupType.ASSOCIATED_DIRECTORIES)
        zips = list(BACKUP_PATH.glob("*.zip"))
        self.assertEqual(len(zips), 1)
        with zipfile.ZipFile(zips[0]) as zf:
            names = zf.namelist()
        self.assertTrue(any("m1_file.txt" in n for n in names))

    def test_create_backup_is_export_naming(self):
        snap = _make_snapshot("ExpSnap", self._src, n=1)
        mgr = self._manager(snap)
        mgr.create()
        BACKUP_PATH.mkdir(parents=True, exist_ok=True)
        mgr.create_backup(BACKUP_PATH, "export", BackupType.SNAPSHOT_DIRECTORY, is_export=True)
        zips = list(BACKUP_PATH.glob("*.zip"))
        self.assertEqual(len(zips), 1)
        self.assertTrue(zips[0].name.startswith("export_"))
        # Non-export backups have "backup_" prefix
        BACKUP_PATH2 = TEST_LOCAL_ROOT / "backups2"
        BACKUP_PATH2.mkdir()
        mgr.create_backup(BACKUP_PATH2, "prefix2", BackupType.SNAPSHOT_DIRECTORY, is_export=False)
        zips2 = list(BACKUP_PATH2.glob("*.zip"))
        self.assertTrue(zips2[0].name.startswith("backup_prefix2"))

    def test_update_from_actions_list(self):
        src_sorted = sorted(self._src)
        snap = _make_snapshot("ActionsSnap", src_sorted, n=2)
        mgr = self._manager(snap)
        mgr.create()

        snap_new = snap.clone()
        removed_assoc = snap_new.directories.pop(0)
        snap_new.directories.append(
            SnapDirAssociation(index=99, original_path=str(src_sorted[2]), folder_id="added999")
        )
        edits = SnapshotUtils.get_edits_between_snapshots(snap, snap_new)
        mgr2 = SnapshotManager(snap_new, CATALOGUE_PATH)
        mgr2.update_from_actions_list(edits)

        self.assertFalse((mgr.path_snapshot / removed_assoc.directory_name).exists())
        self.assertTrue((mgr.path_snapshot / snap_new.directories[-1].directory_name).exists())


# ===========================================================================
# TestSnapshotCatalogueTestCase
# ===========================================================================

class TestSnapshotCatalogueTestCase(unittest.TestCase):
    def setUp(self):
        CATALOGUE_PATH.mkdir(parents=True, exist_ok=True)
        SOURCE_DATA_PATH.mkdir(parents=True, exist_ok=True)
        BACKUP_PATH.mkdir(parents=True, exist_ok=True)
        INSTALL_DEST_PATH.mkdir(parents=True, exist_ok=True)
        self._src = _create_source_dirs(SOURCE_DATA_PATH, ["c1", "c2", "c3"])
        self.settings = SnapshotSettings(
            backup_path=BACKUP_PATH,
            backup_pre_install=True,
            backup_pre_modify=True,
            backup_pre_delete=True,
        )
        self.cat = SnapshotCatalogue(CATALOGUE_PATH, settings=self.settings)

    def tearDown(self):
        shutil.rmtree(TEST_LOCAL_ROOT, ignore_errors=True)

    def test_catalogue_creates_directory(self):
        new_path = TEST_LOCAL_ROOT / "new_cat"
        cat = SnapshotCatalogue(new_path)
        self.assertTrue(new_path.exists())

    def test_set_catalogue_path(self):
        new_path = TEST_LOCAL_ROOT / "moved_cat"
        self.cat.set_catalogue_path(new_path)
        self.assertTrue(new_path.exists())
        self.assertEqual(self.cat.path_catalogue, new_path)

    def test_add_get_all_get_by_id_exists(self):
        self.assertEqual(len(self.cat.get_all()), 0)
        snap = _make_snapshot("CatSnap1", self._src, n=1)
        self.cat.add(snap)
        self.assertEqual(len(self.cat.get_all()), 1)
        self.assertTrue(self.cat.exists(snap.id))
        self.assertFalse(self.cat.exists("nonexistent"))
        retrieved = self.cat.get_by_id(snap.id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.id, snap.id)
        self.assertIsNone(self.cat.get_by_id("nonexistent"))

    def test_add_multiple(self):
        for i in range(3):
            self.cat.add(_make_snapshot(f"Multi{i}", self._src, n=1))
        self.assertEqual(len(self.cat.get_all()), 3)

    def test_delete_removes_from_catalogue(self):
        snap = _make_snapshot("DelSnap", self._src, n=1)
        self.cat.add(snap)
        self.assertTrue(self.cat.exists(snap.id))
        self.cat.delete(snap)
        self.assertFalse(self.cat.exists(snap.id))

    def test_delete_creates_backup_when_enabled(self):
        snap = _make_snapshot("DelBck", self._src, n=1)
        self.cat.add(snap)
        self.cat.delete(snap)
        backups = list(BACKUP_PATH.glob("backup_beforeDelete_*.zip"))
        self.assertEqual(len(backups), 1)

    def test_get_snap_directory_path(self):
        snap = _make_snapshot("DirPath", self._src, n=1)
        self.cat.add(snap)
        path = self.cat.get_snap_directory_path(snap)
        self.assertIsNotNone(path)
        self.assertTrue(path.exists())

    def test_get_snap_directory_path_nonexistent(self):
        snap = Snapshot(id="ghost_id", name="X", desc="")
        self.assertIsNone(self.cat.get_snap_directory_path(snap))

    def test_install_copies_content_back(self):
        snap = _make_snapshot("InstallSnap", self._src, n=1)
        self.cat.add(snap)
        target = Path(snap.directories[0].original_path)
        (target / "stale.txt").write_text("stale")
        self.cat.install(snap)
        self.assertFalse((target / "stale.txt").exists())
        self.assertTrue((target / "c1_file.txt").exists())
        updated = self.cat.get_by_id(snap.id)
        self.assertIsNotNone(updated.date_last_used)

    def test_install_creates_backup_when_enabled(self):
        snap = _make_snapshot("InstBck", self._src, n=1)
        self.cat.add(snap)
        self.cat.install(snap)
        self.assertEqual(len(list(BACKUP_PATH.glob("backup_preinstall_*.zip"))), 1)

    def test_update_snapshot_by_objs(self):
        src_sorted = sorted(self._src)
        old = _make_snapshot("UpdateOld", src_sorted, n=2)
        self.cat.add(old)
        new = old.clone()
        new.name = "UpdateNew"
        new.directories.pop(0)
        new.directories.append(
            SnapDirAssociation(index=99, original_path=str(src_sorted[2]), folder_id=gen_random_string(6))
        )
        self.cat.update_snapshot_by_objs(old, new)
        updated = self.cat.get_by_id(new.id)
        self.assertEqual(updated.name, "UpdateNew")
        self.assertEqual(len(updated.directories), 2)
        paths = {d.original_path for d in updated.directories}
        self.assertIn(src_sorted[2].as_posix(), paths)
        self.assertNotIn(src_sorted[0].as_posix(), paths)

    def test_update_snapshot_creates_backup_when_enabled(self):
        snap = _make_snapshot("UpdBck", self._src, n=1)
        self.cat.add(snap)
        clone = snap.clone()
        clone.name = "UpdBckChanged"
        self.cat.update_snapshot_by_objs(snap, clone)
        self.assertEqual(len(list(BACKUP_PATH.glob("backup_beforeEdit_*.zip"))), 1)

    def test_duplicate_by_id(self):
        snap = _make_snapshot("DupById", self._src, n=1)
        self.cat.add(snap)
        self.cat.duplicate_by_id(snap.id)
        all_snaps = self.cat.get_all()
        self.assertEqual(len(all_snaps), 2)
        copy_snap = next(s for s in all_snaps if s.id != snap.id)
        self.assertIn("Copy", copy_snap.name)

    def test_duplicate_by_id_raises_on_nonexistent(self):
        with self.assertRaises(ValueError):
            self.cat.duplicate_by_id("nonexistent_id")

    def test_export_and_import_snapshot(self):
        snap = _make_snapshot("ExpImpSnap", self._src, n=1)
        self.cat.add(snap)

        export_dir = TEST_LOCAL_ROOT / "exp_imp"
        export_dir.mkdir(parents=True)
        self.cat.export_snapshot(snap.id, export_dir)
        zips = list(export_dir.glob("*.zip"))
        self.assertEqual(len(zips), 1)

        self.cat.delete(snap)
        self.assertFalse(self.cat.exists(snap.id))

        self.cat.import_snapshot(zips[0])
        self.assertTrue(self.cat.exists(snap.id))
        imp = self.cat.get_by_id(snap.id)
        self.assertEqual(imp.name, snap.name)

    def test_import_snapshot_duplicate_id_raises(self):
        snap = _make_snapshot("DupImpSnap", self._src, n=1)
        self.cat.add(snap)
        export_dir = TEST_LOCAL_ROOT / "dup_exp"
        export_dir.mkdir(parents=True)
        self.cat.export_snapshot(snap.id, export_dir)
        zip_path = list(export_dir.glob("*.zip"))[0]
        with self.assertRaises(ValueError) as ctx:
            self.cat.import_snapshot(zip_path)
        self.assertIn("already exists", str(ctx.exception))

    def test_import_snapshot_invalid_zip(self):
        bad = TEST_LOCAL_ROOT / "bad.zip"
        bad.write_text("not a zip")
        with self.assertRaises(ValueError):
            self.cat.import_snapshot(bad)

    def test_import_snapshot_non_zip_extension(self):
        notzip = TEST_LOCAL_ROOT / "file.txt"
        notzip.write_text("x")
        with self.assertRaises(ValueError):
            self.cat.import_snapshot(notzip)

    def test_import_snapshot_missing_json(self):
        empty_zip = TEST_LOCAL_ROOT / "empty.zip"
        with zipfile.ZipFile(empty_zip, "w") as zf:
            zf.writestr("dummy.txt", "hello")
        with self.assertRaises(ValueError) as ctx:
            self.cat.import_snapshot(empty_zip)
        self.assertIn("snapshot json file", str(ctx.exception))

    def test_export_and_import_catalogue(self):
        for i in range(3):
            self.cat.add(_make_snapshot(f"CatExp{i}", self._src, n=1))
        exp_dir = TEST_LOCAL_ROOT / "cat_export"
        exp_dir.mkdir(parents=True)
        self.cat.export_catalogue(exp_dir, "cat.zip")
        self.assertTrue((exp_dir / "cat.zip").exists())

        for s in self.cat.get_all():
            self.cat.delete(s)
        self.assertEqual(len(self.cat.get_all()), 0)
        self.cat.import_catalogue(exp_dir / "cat.zip")
        self.assertEqual(len(self.cat.get_all()), 3)

    def test_export_catalogue_empty_logs_warning(self):
        exp_dir = TEST_LOCAL_ROOT / "empty_cat_exp"
        exp_dir.mkdir(parents=True)
        with self.assertLogs(level="WARNING"):
            self.cat.export_catalogue(exp_dir, "empty.zip")

    def test_import_catalogue_skips_existing(self):
        s1 = _make_snapshot("Skip1", self._src, n=1)
        s2 = _make_snapshot("Skip2", self._src, n=1)
        self.cat.add(s1)
        self.cat.add(s2)
        exp_dir = TEST_LOCAL_ROOT / "skip_cat"
        exp_dir.mkdir()
        self.cat.export_catalogue(exp_dir, "skip.zip")
        self.cat.delete(s2)
        self.assertEqual(len(self.cat.get_all()), 1)

        with patch("pylizlib.core.log.pylizLogger.logger.info") as mock_info:
            self.cat.import_catalogue(exp_dir / "skip.zip")
            mock_info.assert_any_call(f"Snapshot with ID '{s1.id}' already exists. Skipping import.")
            mock_info.assert_any_call(f"Successfully imported snapshot with ID '{s2.id}'.")
        self.assertEqual(len(self.cat.get_all()), 2)

    def test_import_catalogue_invalid_zip(self):
        bad = TEST_LOCAL_ROOT / "bad_cat.zip"
        bad.write_text("not a zip")
        with self.assertRaises(ValueError):
            self.cat.import_catalogue(bad)

    def test_export_assoc_dirs(self):
        snap = _make_snapshot("ExpAssoc", self._src, n=2)
        self.cat.add(snap)
        exp_dir = TEST_LOCAL_ROOT / "assoc_exp"
        exp_dir.mkdir()
        self.cat.export_assoc_dirs(snap.id, exp_dir)
        zips = list(exp_dir.glob("*.zip"))
        self.assertEqual(len(zips), 1)
        self.assertIn("_ad_", zips[0].name)

    def test_export_assoc_dirs_nonexistent_raises(self):
        with self.assertRaises(ValueError):
            self.cat.export_assoc_dirs("nonexistent_id", TEST_LOCAL_ROOT)

    def test_export_snapshot_nonexistent_raises(self):
        with self.assertRaises(ValueError):
            self.cat.export_snapshot("nonexistent_id", TEST_LOCAL_ROOT)

    def test_update_assoc_with_installed(self):
        snap = _make_snapshot("UpdAssoc", self._src, n=1)
        self.cat.add(snap)
        self.cat.install(snap)
        original_dir = Path(snap.directories[0].original_path)
        (original_dir / "added_after_install.txt").write_text("added")
        self.cat.update_assoc_with_installed(snap.id)
        snap_dir = self.cat.get_snap_directory_path(snap)
        internal = snap_dir / snap.directories[0].directory_name
        self.assertTrue((internal / "added_after_install.txt").exists())

    def test_update_assoc_with_installed_raises_on_nonexistent(self):
        with self.assertRaises(ValueError):
            self.cat.update_assoc_with_installed("nonexistent_id")

    def test_remove_installed_copies(self):
        install1 = INSTALL_DEST_PATH / "rem1"
        install2 = INSTALL_DEST_PATH / "rem2"
        install1.mkdir(parents=True)
        install2.mkdir(parents=True)
        (install1 / "f.txt").write_text("x")
        (install2 / "f.txt").write_text("x")
        _reset_index()
        snap = Snapshot(
            id=gen_random_string(8), name="RemInstalled", desc="",
            directories=[
                SnapDirAssociation(index=1, original_path=str(install1), folder_id="ri1"),
                SnapDirAssociation(index=2, original_path=str(install2), folder_id="ri2"),
            ],
        )
        self.cat.add(snap)
        self.cat.remove_installed_copies(snap.id)
        self.assertFalse(install1.exists())
        self.assertFalse(install2.exists())

    def test_remove_installed_copies_warns_on_nonexistent_snap(self):
        with self.assertLogs(level="WARNING"):
            self.cat.remove_installed_copies("nonexistent_id")

    def test_list_backups_returns_entries(self):
        snap = _make_snapshot("ListBackups", self._src, n=1)
        self.cat.add(snap)
        mgr = SnapshotManager(snap, CATALOGUE_PATH, self.settings)
        mgr.create_backup(BACKUP_PATH, "beforeEdit", BackupType.SNAPSHOT_DIRECTORY)
        mgr.create_backup(BACKUP_PATH, "preinstall", BackupType.ASSOCIATED_DIRECTORIES)

        backups = self.cat.list_backups(BACKUP_PATH)
        self.assertGreaterEqual(len(backups), 2)

        types = {b.backup_type for b in backups}
        self.assertIn(BackupType.SNAPSHOT_DIRECTORY, types)
        self.assertIn(BackupType.ASSOCIATED_DIRECTORIES, types)

        for backup in backups:
            self.assertTrue(backup.path.exists())
            self.assertTrue(backup.file_name.endswith(".zip"))

    def test_list_backups_invalid_folder_raises(self):
        with self.assertRaises(ValueError):
            self.cat.list_backups(TEST_LOCAL_ROOT / "does_not_exist")

    def test_restore_backup_snapshot_directory(self):
        snap = _make_snapshot("RestoreSD", self._src, n=1)
        self.cat.add(snap)

        mgr = SnapshotManager(snap, CATALOGUE_PATH, self.settings)
        mgr.create_backup(BACKUP_PATH, "beforeDelete", BackupType.SNAPSHOT_DIRECTORY)
        backup_zip = sorted(BACKUP_PATH.glob("*_*_sd_*.zip"))[-1]

        # Destroy current snapshot directory and restore from backup
        shutil.rmtree(CATALOGUE_PATH / snap.id)
        self.assertFalse((CATALOGUE_PATH / snap.id).exists())

        self.cat.restore_backup(backup_zip)

        self.assertTrue((CATALOGUE_PATH / snap.id).exists())
        restored = self.cat.get_by_id(snap.id)
        self.assertIsNotNone(restored)
        self.assertEqual(restored.id, snap.id)

    def test_restore_backup_associated_directories(self):
        snap = _make_snapshot("RestoreAD", self._src, n=1)
        self.cat.add(snap)

        source_dir = Path(snap.directories[0].original_path)
        target_file = source_dir / "c1_file.txt"
        original_content = target_file.read_text()

        mgr = SnapshotManager(snap, CATALOGUE_PATH, self.settings)
        mgr.create_backup(BACKUP_PATH, "preinstall", BackupType.ASSOCIATED_DIRECTORIES)
        backup_zip = sorted(BACKUP_PATH.glob("*_*_ad_*.zip"))[-1]

        # Corrupt content then restore
        target_file.write_text("CORRUPTED")
        self.assertEqual(target_file.read_text(), "CORRUPTED")

        self.cat.restore_backup(backup_zip)

        self.assertEqual(target_file.read_text(), original_content)

    def test_restore_backup_unknown_type_raises(self):
        unknown_zip = BACKUP_PATH / "unknown_backup.zip"
        with zipfile.ZipFile(unknown_zip, "w") as zf:
            zf.writestr("dummy.txt", "x")

        with self.assertRaises(ValueError):
            self.cat.restore_backup(unknown_zip)

    def test_restore_backup_associated_requires_existing_snapshot(self):
        snap = _make_snapshot("RestoreADMissingSnap", self._src, n=1)
        self.cat.add(snap)
        mgr = SnapshotManager(snap, CATALOGUE_PATH, self.settings)
        mgr.create_backup(BACKUP_PATH, "preinstall", BackupType.ASSOCIATED_DIRECTORIES)
        backup_zip = sorted(BACKUP_PATH.glob("*_*_ad_*.zip"))[-1]

        # Remove snapshot metadata so restore cannot map folders
        shutil.rmtree(CATALOGUE_PATH / snap.id)

        with self.assertRaises(ValueError):
            self.cat.restore_backup(backup_zip)


# ===========================================================================
# TestSnapshotSearcherTestCase
# ===========================================================================

class TestSnapshotSearcherTestCase(unittest.TestCase):
    def setUp(self):
        CATALOGUE_PATH.mkdir(parents=True, exist_ok=True)
        SOURCE_DATA_PATH.mkdir(parents=True, exist_ok=True)

        dir1 = SOURCE_DATA_PATH / "srch1"
        dir1.mkdir()
        (dir1 / "fileA.txt").write_text("Hello world\nThis is a test file.")
        (dir1 / "fileB.txt").write_text("Another file with test content.\nHello again.")

        dir2 = SOURCE_DATA_PATH / "srch2"
        dir2.mkdir()
        (dir2 / "fileC.log").write_text("Log file with value=12345\nSome data.")
        (dir2 / "fileD.txt").write_text("No interesting content here.")
        (dir2 / "binary.bin").write_bytes(b"\x80\x81\x82\xff")

        _reset_index()
        self.snap = Snapshot(
            id="search-snap-id",
            name="SearchSnap",
            desc="",
            directories=[
                SnapDirAssociation(index=1, original_path=str(dir1), folder_id="sd1"),
                SnapDirAssociation(index=2, original_path=str(dir2), folder_id="sd2"),
            ],
            author="Test",
        )
        self.catalogue = SnapshotCatalogue(CATALOGUE_PATH)
        self.catalogue.add(self.snap)
        self.searcher = SnapshotSearcher(self.catalogue)

    def tearDown(self):
        shutil.rmtree(TEST_LOCAL_ROOT, ignore_errors=True)

    def test_content_text_found(self):
        params = SnapshotSearchParams(query="Hello", search_target=SearchTarget.FILE_CONTENT, query_type=QueryType.TEXT)
        results = self.searcher.search(self.snap, params)
        self.assertEqual(len(results), 2)
        names = {r.file_path.name for r in results}
        self.assertIn("fileA.txt", names)
        self.assertIn("fileB.txt", names)

    def test_content_text_not_found(self):
        params = SnapshotSearchParams(query="IMPOSSIBLE_STRING_xyz123")
        results = self.searcher.search(self.snap, params)
        self.assertEqual(len(results), 0)

    def test_content_regex(self):
        params = SnapshotSearchParams(
            query=r"value=\d+",
            search_target=SearchTarget.FILE_CONTENT,
            query_type=QueryType.REGEX,
        )
        results = self.searcher.search(self.snap, params)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].file_path.name, "fileC.log")

    def test_content_invalid_regex_returns_empty(self):
        params = SnapshotSearchParams(query=r"[invalid", query_type=QueryType.REGEX)
        self.assertEqual(self.searcher.search(self.snap, params), [])

    def test_content_extension_filter(self):
        params = SnapshotSearchParams(query="file", extensions=[".txt"])
        results = self.searcher.search(self.snap, params)
        for r in results:
            self.assertEqual(r.file_path.suffix, ".txt")

    def test_content_binary_file_skipped(self):
        params = SnapshotSearchParams(query="binary")
        results = self.searcher.search(self.snap, params)
        self.assertIsInstance(results, list)

    def test_filename_text(self):
        params = SnapshotSearchParams(
            query="fileA",
            search_target=SearchTarget.FILE_NAME,
            query_type=QueryType.TEXT,
        )
        results = self.searcher.search(self.snap, params)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].file_path.name, "fileA.txt")
        self.assertIsNone(results[0].line_number)
        self.assertIsNone(results[0].line_content)

    def test_filename_regex(self):
        params = SnapshotSearchParams(
            query=r"file[AB]\.txt$",
            search_target=SearchTarget.FILE_NAME,
            query_type=QueryType.REGEX,
        )
        results = self.searcher.search(self.snap, params)
        names = {r.file_path.name for r in results}
        self.assertEqual(names, {"fileA.txt", "fileB.txt"})

    def test_filename_extension_filter(self):
        params = SnapshotSearchParams(query="fileC", search_target=SearchTarget.FILE_NAME, extensions=[".log"])
        self.assertEqual(len(self.searcher.search(self.snap, params)), 1)
        params2 = SnapshotSearchParams(query="fileC", search_target=SearchTarget.FILE_NAME, extensions=[".txt"])
        self.assertEqual(len(self.searcher.search(self.snap, params2)), 0)

    def test_search_list_across_snapshots(self):
        snap2_dir = SOURCE_DATA_PATH / "srch3"
        snap2_dir.mkdir()
        (snap2_dir / "extra.txt").write_text("Hello from snap2")
        _reset_index()
        snap2 = Snapshot(
            id="search-snap2-id", name="SearchSnap2", desc="",
            directories=[SnapDirAssociation(index=1, original_path=str(snap2_dir), folder_id="sd3")],
        )
        self.catalogue.add(snap2)

        params = SnapshotSearchParams(query="Hello", search_target=SearchTarget.FILE_CONTENT)
        results = self.searcher.search_list([self.snap, snap2], params)
        snap_names = {r.snapshot_name for r in results}
        self.assertIn("SearchSnap", snap_names)
        self.assertIn("SearchSnap2", snap_names)

    def test_search_progress_callback(self):
        calls = []
        def cb(filename, total, processed):
            calls.append((filename, total, processed))
        params = SnapshotSearchParams(query="Hello", search_target=SearchTarget.FILE_CONTENT)
        self.searcher.search(self.snap, params, on_progress=cb)
        self.assertGreater(len(calls), 0)
        last = calls[-1]
        self.assertEqual(last[1], last[2])

    def test_search_nonexistent_snapshot_path_returns_empty(self):
        ghost_snap = Snapshot(
            id="ghost_id_xyz", name="Ghost", desc="",
            directories=[SnapDirAssociation(index=1, original_path="/nonexistent/path", folder_id="g1")],
        )
        params = SnapshotSearchParams(query="anything")
        with self.assertLogs(level="WARNING"):
            results = self.searcher.search(ghost_snap, params)
        self.assertEqual(results, [])


# ===========================================================================
# TestIntegrationScenariosTestCase
# ===========================================================================

class TestIntegrationScenariosTestCase(unittest.TestCase):
    """End-to-end scenarios using real downloaded images."""

    def setUp(self):
        CATALOGUE_PATH.mkdir(parents=True, exist_ok=True)
        SOURCE_DATA_PATH.mkdir(parents=True, exist_ok=True)
        BACKUP_PATH.mkdir(parents=True, exist_ok=True)
        self.settings = SnapshotSettings(backup_path=BACKUP_PATH)
        self.cat = SnapshotCatalogue(CATALOGUE_PATH, settings=self.settings)

    def tearDown(self):
        shutil.rmtree(TEST_LOCAL_ROOT, ignore_errors=True)

    def test_scenario_a_full_lifecycle_with_images(self):
        """Create → install → modify source → update internal → reinstall."""
        src = _downloader.create_sample_directory(
            SOURCE_DATA_PATH, "scene_a", image_count=2,
            extra_text_files={"meta.txt": "version=1"},
        )
        _reset_index()
        snap = Snapshot(
            id=gen_random_string(10), name="ScenarioA", desc="",
            directories=[SnapDirAssociation(index=1, original_path=str(src), folder_id="sca1")],
        )
        self.cat.add(snap)
        self.cat.install(snap)
        self.assertTrue((src / "meta.txt").exists())

        # Modify source
        (src / "meta.txt").write_text("version=2")
        (src / "extra.jpg").write_bytes(b"\xff\xd8\xff" + b"\x00" * 100)

        # Update internal copy
        self.cat.update_assoc_with_installed(snap.id)
        snap_dir = self.cat.get_snap_directory_path(snap)
        internal = snap_dir / snap.directories[0].directory_name
        self.assertEqual((internal / "meta.txt").read_text(), "version=2")
        self.assertTrue((internal / "extra.jpg").exists())

        # Reinstall should propagate version=2
        (src / "meta.txt").unlink()
        self.cat.install(snap)
        self.assertTrue((src / "meta.txt").exists())
        self.assertEqual((src / "meta.txt").read_text(), "version=2")

    def test_scenario_b_multi_snap_sort_export_reimport(self):
        """Multiple snapshots: sort, export catalogue, re-import."""
        dirs = []
        for i, size in enumerate([100, 5_000, 50_000]):
            d = SOURCE_DATA_PATH / f"scb_{i}"
            d.mkdir()
            (d / f"file_{i}.txt").write_text("x" * size)
            dirs.append(d)

        for i, d in enumerate(dirs):
            _reset_index()
            s = Snapshot(
                id=gen_random_string(8), name=f"ScenB_{i}", desc="",
                directories=[SnapDirAssociation(index=1, original_path=str(d), folder_id=f"sb{i}")],
            )
            self.cat.add(s)

        all_snaps = self.cat.get_all()
        sorted_snaps = SnapshotUtils.sort_snapshots(all_snaps, SnapshotSortKey.NAME)
        names = [s.name for s in sorted_snaps]
        self.assertEqual(names, sorted(names, key=str.lower))

        exp_dir = TEST_LOCAL_ROOT / "scb_export"
        exp_dir.mkdir()
        self.cat.export_catalogue(exp_dir, "scb.zip")
        self.assertTrue((exp_dir / "scb.zip").exists())

        for s in self.cat.get_all():
            self.cat.delete(s)
        self.assertEqual(len(self.cat.get_all()), 0)
        self.cat.import_catalogue(exp_dir / "scb.zip")
        self.assertEqual(len(self.cat.get_all()), 3)

    def test_scenario_c_duplicate_independence(self):
        """Duplicate → edit duplicate → verify originals unchanged (BUG-2 regression)."""
        src = SOURCE_DATA_PATH / "scc"
        src.mkdir()
        (src / "data.txt").write_text("original data")
        _reset_index()
        original = Snapshot(
            id=gen_random_string(8), name="SccOriginal", desc="",
            directories=[SnapDirAssociation(index=1, original_path=str(src), folder_id="scc1")],
        )
        self.cat.add(original)
        original_id_before = original.id

        self.cat.duplicate_by_id(original.id)
        # BUG-2 regression: original must remain unchanged
        self.assertEqual(original.id, original_id_before)

        all_snaps = self.cat.get_all()
        copy_snap = next(s for s in all_snaps if s.id != original.id)
        copy_snap.name = "SccCopy_modified"
        SnapshotManager(copy_snap, CATALOGUE_PATH).update_json_base_fields()

        orig_from_cat = self.cat.get_by_id(original.id)
        self.assertEqual(orig_from_cat.name, "SccOriginal")

    def test_scenario_d_real_images_survive_snapshot_roundtrip(self):
        """Images downloaded from Picsum must survive add/install with identical bytes."""
        img_dir = _downloader.create_sample_directory(
            SOURCE_DATA_PATH, "real_imgs", image_count=3,
        )
        _reset_index()
        snap = Snapshot(
            id=gen_random_string(8), name="RealImages", desc="",
            directories=[SnapDirAssociation(index=1, original_path=str(img_dir), folder_id="ri1")],
        )
        self.cat.add(snap)
        snap_dir = self.cat.get_snap_directory_path(snap)
        internal = snap_dir / snap.directories[0].directory_name

        for orig in sorted(img_dir.glob("*.jpg")):
            copy = internal / orig.name
            self.assertTrue(copy.exists(), f"Image {orig.name} not in snapshot")
            self.assertEqual(orig.read_bytes(), copy.read_bytes(), f"Image {orig.name} content differs")

    def test_scenario_e_search_still_works_after_source_removal(self):
        """Snapshot internal copy should still be searchable after source dir removal."""
        src = SOURCE_DATA_PATH / "sce"
        src.mkdir()
        (src / "searchable.txt").write_text("find_this_unique_string")

        _reset_index()
        snap = Snapshot(
            id=gen_random_string(8), name="SceSnap", desc="",
            directories=[SnapDirAssociation(index=1, original_path=str(src), folder_id="sce1")],
        )
        self.cat.add(snap)
        searcher = SnapshotSearcher(self.cat)
        params = SnapshotSearchParams(query="find_this_unique_string", search_target=SearchTarget.FILE_CONTENT)

        results_before = searcher.search(snap, params)
        self.assertGreater(len(results_before), 0)

        shutil.rmtree(src)
        results_after = searcher.search(snap, params)
        self.assertGreater(len(results_after), 0)


# ===========================================================================
# TestBugFixesTestCase
# ===========================================================================

class TestBugFixesTestCase(unittest.TestCase):
    """Explicit regression tests for all known bugs that were fixed."""

    def setUp(self):
        TEST_LOCAL_ROOT.mkdir(parents=True, exist_ok=True)
        SOURCE_DATA_PATH.mkdir(parents=True, exist_ok=True)
        _create_source_dirs(SOURCE_DATA_PATH, ["b1", "b2"])
        CATALOGUE_PATH.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(TEST_LOCAL_ROOT, ignore_errors=True)

    def test_bug1_snapshot_date_created_not_shared(self):
        """
        BUG-1 (Snapshot): date_created was evaluated once at class definition →
        all instances shared the same datetime object.
        After fix: each instance gets a fresh datetime.
        """
        first = Snapshot(id="x", name="x", desc="")
        time.sleep(0.02)
        second = Snapshot(id="y", name="y", desc="")
        self.assertLessEqual(first.date_created, second.date_created)
        self.assertIsNot(first.date_created, second.date_created)

    def test_bug1_snap_edit_action_timestamp_not_shared(self):
        """BUG-1 (SnapEditAction): same shared-default bug."""
        e1 = SnapEditAction(SnapEditType.ADD_DIR)
        time.sleep(0.02)
        e2 = SnapEditAction(SnapEditType.REMOVE_DIR)
        self.assertIsNot(e1.timestamp, e2.timestamp)

    def test_bug2_duplicate_preserves_original_snapshot(self):
        """
        BUG-2: SnapshotManager.duplicate() used a reference (`new_snap = self.snapshot`)
        instead of a clone, so self.snapshot.id was silently mutated.
        After fix: self.snapshot remains unchanged.
        """
        src = list(p for p in SOURCE_DATA_PATH.iterdir() if p.is_dir())
        snap = _make_snapshot("BugOriginal", src, n=1)
        mgr = SnapshotManager(snap, CATALOGUE_PATH, SnapshotSettings())
        mgr.create()

        original_id = snap.id
        original_name = snap.name
        mgr.duplicate()

        self.assertEqual(snap.id, original_id, "BUG-2: duplicate() must NOT change self.snapshot.id")
        self.assertEqual(snap.name, original_name, "BUG-2: duplicate() must NOT change self.snapshot.name")

        # Original JSON must still contain the original ID
        orig_json = SnapshotSerializer.from_json(mgr.path_snapshot_json)
        self.assertEqual(orig_json.id, original_id)

    def test_bug3_from_json_parses_date_last_used(self):
        """
        BUG-3: from_json() listed "date_last_installed" (non-existent field) in its
        datetime-parsing loop, while date_last_used was separately handled.
        The dead key has been removed and date_last_used round-trips correctly.
        """
        src = list(p for p in SOURCE_DATA_PATH.iterdir() if p.is_dir())
        snap = _make_snapshot("Bug3", src, n=1)
        expected = datetime(2025, 12, 25, 10, 30, 0)
        snap.date_last_used = expected

        json_path = TEST_LOCAL_ROOT / "bug3.json"
        SnapshotSerializer.to_json(snap, json_path)
        loaded = SnapshotSerializer.from_json(json_path)

        self.assertIsNotNone(loaded.date_last_used)
        self.assertEqual(loaded.date_last_used, expected)


if __name__ == "__main__":
    unittest.main(argv=["first-arg-is-ignored"], exit=False)
