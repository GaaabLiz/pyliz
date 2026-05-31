"""
Unit tests for pylizlib.core.os.snap.utils

Covers:
    - SnapshotUtils.gen_random_snap
    - SnapshotUtils.get_snapshot_path / get_snapshot_json_path
    - SnapshotUtils.get_snapshot_from_path  (happy path + all error branches)
    - SnapshotUtils.get_edits_between_snapshots  (no change, add, remove, both)
    - SnapshotUtils.sort_snapshots (by name, by date, None values at end, by mb_size)
"""

import unittest
from datetime import datetime, timedelta
from pathlib import Path

from pylizlib.core.data.gen import gen_random_string
from pylizlib.core.os.snap.domain import (
    SnapDirAssociation,
    SnapEditType,
    Snapshot,
    SnapshotSortKey,
)
from pylizlib.core.os.snap.serializer import SnapshotSerializer
from pylizlib.core.os.snap.utils import SnapshotUtils
from test.core.os.snap.conftest import (
    CATALOGUE_PATH,
    SOURCE_DATA_PATH,
    TEST_LOCAL_ROOT,
    create_source_dirs,
    make_snapshot,
    reset_index,
    setup_test_dirs,
    teardown_test_dirs,
)


class TestSnapshotUtilsPaths(unittest.TestCase):
    """Path construction helpers."""

    def setUp(self):
        setup_test_dirs()

    def tearDown(self):
        teardown_test_dirs()

    def test_get_snapshot_path(self):
        p = SnapshotUtils.get_snapshot_path("myid", CATALOGUE_PATH)
        self.assertEqual(p, CATALOGUE_PATH / "myid")

    def test_get_snapshot_json_path(self):
        p = SnapshotUtils.get_snapshot_json_path("myid", CATALOGUE_PATH, "snap.json")
        self.assertEqual(p, CATALOGUE_PATH / "myid" / "snap.json")


class TestSnapshotUtilsGetFromPath(unittest.TestCase):
    """get_snapshot_from_path: happy path and all error branches."""

    def setUp(self):
        setup_test_dirs()
        create_source_dirs(SOURCE_DATA_PATH, ["u1", "u2"])

    def tearDown(self):
        teardown_test_dirs()

    def test_raises_value_error_when_path_is_a_file(self):
        f = TEST_LOCAL_ROOT / "a_file.txt"
        f.write_text("x")
        with self.assertRaises(ValueError):
            SnapshotUtils.get_snapshot_from_path(f, "snapshot.json")

    def test_raises_file_not_found_when_directory_missing(self):
        with self.assertRaises(FileNotFoundError):
            SnapshotUtils.get_snapshot_from_path(TEST_LOCAL_ROOT / "ghost", "snapshot.json")

    def test_raises_file_not_found_when_json_missing(self):
        empty_dir = TEST_LOCAL_ROOT / "empty_snap"
        empty_dir.mkdir()
        with self.assertRaises(FileNotFoundError):
            SnapshotUtils.get_snapshot_from_path(empty_dir, "snapshot.json")

    def test_returns_snapshot_on_success(self):
        src_dirs = [p for p in SOURCE_DATA_PATH.iterdir() if p.is_dir()]
        snap = make_snapshot("UtilsSnap", src_dirs, n=1)
        snap_dir = CATALOGUE_PATH / snap.id
        snap_dir.mkdir()
        SnapshotSerializer.to_json(snap, snap_dir / "snapshot.json")

        loaded = SnapshotUtils.get_snapshot_from_path(snap_dir, "snapshot.json")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.id, snap.id)


class TestSnapshotUtilsGenRandom(unittest.TestCase):
    """gen_random_snap produces a valid Snapshot with 3 directories."""

    def setUp(self):
        setup_test_dirs()
        create_source_dirs(SOURCE_DATA_PATH, ["g1", "g2", "g3", "g4"])

    def tearDown(self):
        teardown_test_dirs()

    def test_returns_snapshot_instance_with_correct_id_length(self):
        snap = SnapshotUtils.gen_random_snap(SOURCE_DATA_PATH, id_length=8)
        self.assertIsInstance(snap, Snapshot)
        self.assertEqual(len(snap.id), 8)
        self.assertEqual(len(snap.directories), 3)


class TestSnapshotUtilsEdits(unittest.TestCase):
    """get_edits_between_snapshots covers all four diff cases."""

    def setUp(self):
        setup_test_dirs()
        create_source_dirs(SOURCE_DATA_PATH, ["e1", "e2", "e3"])

    def tearDown(self):
        teardown_test_dirs()

    def test_no_change_returns_empty_list(self):
        src = [p for p in SOURCE_DATA_PATH.iterdir() if p.is_dir()]
        old = make_snapshot("Old", src, n=2)
        new = old.clone()
        self.assertEqual(SnapshotUtils.get_edits_between_snapshots(old, new), [])

    def test_detects_added_directory(self):
        src = sorted(p for p in SOURCE_DATA_PATH.iterdir() if p.is_dir())
        old = make_snapshot("Old", src, n=2)
        new = old.clone()
        new.directories.append(SnapDirAssociation(index=99, original_path=str(src[2]), folder_id="NEW"))
        edits = SnapshotUtils.get_edits_between_snapshots(old, new)
        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0].action_type, SnapEditType.ADD_DIR)

    def test_detects_removed_directory(self):
        src = sorted(p for p in SOURCE_DATA_PATH.iterdir() if p.is_dir())
        old = make_snapshot("Old", src, n=2)
        new = old.clone()
        removed = new.directories.pop(0)
        edits = SnapshotUtils.get_edits_between_snapshots(old, new)
        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0].action_type, SnapEditType.REMOVE_DIR)
        self.assertEqual(edits[0].folder_id_to_remove, removed.folder_id)

    def test_detects_simultaneous_add_and_remove(self):
        src = sorted(p for p in SOURCE_DATA_PATH.iterdir() if p.is_dir())
        old = make_snapshot("Old", src, n=2)
        new = old.clone()
        new.directories.pop(0)
        new.directories.append(SnapDirAssociation(index=99, original_path=str(src[2]), folder_id="NEW2"))
        edits = SnapshotUtils.get_edits_between_snapshots(old, new)
        self.assertEqual(len(edits), 2)
        types = {e.action_type for e in edits}
        self.assertIn(SnapEditType.ADD_DIR, types)
        self.assertIn(SnapEditType.REMOVE_DIR, types)


class TestSnapshotUtilsSort(unittest.TestCase):
    """sort_snapshots covers all sort keys and edge cases."""

    def setUp(self):
        setup_test_dirs()
        create_source_dirs(SOURCE_DATA_PATH, ["s1", "s2", "s3"])

    def tearDown(self):
        teardown_test_dirs()

    def test_sort_by_name_ascending_case_insensitive(self):
        now = datetime.now()
        s1 = Snapshot(id="1", name="Gamma", desc="", date_created=now)
        s2 = Snapshot(id="2", name="alpha", desc="", date_created=now)
        s3 = Snapshot(id="3", name="Beta", desc="", date_created=now)
        result = SnapshotUtils.sort_snapshots([s1, s2, s3], SnapshotSortKey.NAME)
        self.assertEqual([s.name for s in result], ["alpha", "Beta", "Gamma"])

    def test_sort_by_name_descending(self):
        now = datetime.now()
        s1 = Snapshot(id="1", name="Gamma", desc="", date_created=now)
        s2 = Snapshot(id="2", name="alpha", desc="", date_created=now)
        result = SnapshotUtils.sort_snapshots([s1, s2], SnapshotSortKey.NAME, reverse=True)
        self.assertEqual([s.name for s in result], ["Gamma", "alpha"])

    def test_none_values_are_placed_at_end(self):
        now = datetime.now()
        s1 = Snapshot(id="1", name="A", desc="", date_modified=now)
        s2 = Snapshot(id="2", name="B", desc="", date_modified=None)
        s3 = Snapshot(id="3", name="C", desc="", date_modified=now - timedelta(days=1))
        result = SnapshotUtils.sort_snapshots([s1, s2, s3], SnapshotSortKey.DATE_MODIFIED)
        self.assertEqual(result[-1].id, "2")
        self.assertEqual(result[0].id, "3")

    def test_sort_by_assoc_dir_mb_size_ascending(self):
        src = sorted(p for p in SOURCE_DATA_PATH.iterdir() if p.is_dir())
        (src[0] / "small.txt").write_text("x" * 100)
        (src[1] / "medium.txt").write_text("x" * 5_000)
        (src[2] / "large.txt").write_text("x" * 100_000)

        snap_s = make_snapshot("Small", [src[0]], n=1)
        snap_m = make_snapshot("Medium", [src[1]], n=1)
        snap_l = make_snapshot("Large", [src[2]], n=1)

        sorted_asc = SnapshotUtils.sort_snapshots([snap_l, snap_m, snap_s], SnapshotSortKey.ASSOC_DIR_MB_SIZE)
        self.assertEqual([s.name for s in sorted_asc], ["Small", "Medium", "Large"])

    def test_sort_empty_list_returns_empty(self):
        result = SnapshotUtils.sort_snapshots([], SnapshotSortKey.NAME)
        self.assertEqual(result, [])

    def test_sort_single_element_returns_same(self):
        now = datetime.now()
        s = Snapshot(id="1", name="Only", desc="", date_created=now)
        result = SnapshotUtils.sort_snapshots([s], SnapshotSortKey.NAME)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, "1")


if __name__ == "__main__":
    unittest.main()
