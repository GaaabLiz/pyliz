"""
Unit tests for pylizlib.core.os.snap.domain

Covers:
    - SnapDirAssociation: construction, properties, copy_install_to, factory methods
    - SnapEditType / BackupType / SnapshotSortKey enums
    - SnapshotBackupInfo dataclass
    - SnapEditAction: timestamp uniqueness (BUG-1 regression)
    - SnapshotSettings: defaults and backup-enabled properties
    - Snapshot: all properties, data CRUD, clone deep-copy (BUG-1 regression)
"""

import shutil
import time
import unittest
from pathlib import Path

from pylizlib.core.data.gen import gen_random_string
from pylizlib.core.os.snap.domain import (
    BackupType,
    SnapDirAssociation,
    SnapEditAction,
    SnapEditType,
    Snapshot,
    SnapshotBackupInfo,
    SnapshotSettings,
    SnapshotSortKey,
)
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


class TestSnapDirAssociationConstruction(unittest.TestCase):
    """Tests for SnapDirAssociation initialisation and computed properties."""

    def setUp(self):
        setup_test_dirs()

    def tearDown(self):
        teardown_test_dirs()

    def test_directory_name_format(self):
        d = SOURCE_DATA_PATH / "mydir"
        d.mkdir()
        assoc = SnapDirAssociation(index=5, original_path=str(d), folder_id="abc")
        self.assertEqual(assoc.directory_name, "5-mydir")

    def test_original_path_normalised_to_posix(self):
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

    def test_mb_size_zero_when_directory_missing(self):
        assoc = SnapDirAssociation(
            index=1,
            original_path=str(SOURCE_DATA_PATH / "ghost_dir"),
            folder_id="g",
        )
        self.assertEqual(assoc.mb_size, 0.0)

    def test_mb_size_preserved_when_explicitly_provided(self):
        d = SOURCE_DATA_PATH / "preserved"
        d.mkdir()
        assoc = SnapDirAssociation(index=1, original_path=str(d), folder_id="p", mb_size=42.0)
        self.assertEqual(assoc.mb_size, 42.0)

    def test_next_index_increments(self):
        reset_index()
        i1 = SnapDirAssociation.next_index()
        i2 = SnapDirAssociation.next_index()
        self.assertEqual(i2, i1 + 1)


class TestSnapDirAssociationCopyInstallTo(unittest.TestCase):
    """Tests for SnapDirAssociation.copy_install_to."""

    def setUp(self):
        setup_test_dirs()

    def tearDown(self):
        teardown_test_dirs()

    def test_copies_files_and_subdirectories(self):
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

    def test_creates_destination_if_missing(self):
        src = SOURCE_DATA_PATH / "newdest"
        src.mkdir()
        (src / "x.txt").write_text("x")
        target = TEST_LOCAL_ROOT / "nonexistent_parent" / "sub"
        assoc = SnapDirAssociation(index=1, original_path=str(src), folder_id="nd")
        assoc.copy_install_to(target)
        self.assertTrue((target / assoc.directory_name).exists())


class TestSnapDirAssociationFactoryMethods(unittest.TestCase):
    """Tests for gen_random and gen_random_list factory methods."""

    def setUp(self):
        setup_test_dirs()
        for i in range(5):
            (SOURCE_DATA_PATH / f"rnd{i}").mkdir(exist_ok=True)

    def tearDown(self):
        teardown_test_dirs()

    def test_gen_random_returns_instance_with_correct_id_length(self):
        assoc = SnapDirAssociation.gen_random(SOURCE_DATA_PATH, folder_id_length=4)
        self.assertIsInstance(assoc, SnapDirAssociation)
        self.assertEqual(len(assoc.folder_id), 4)

    def test_gen_random_list_returns_correct_count(self):
        result = SnapDirAssociation.gen_random_list(3, SOURCE_DATA_PATH)
        self.assertEqual(len(result), 3)
        self.assertTrue(all(isinstance(a, SnapDirAssociation) for a in result))


class TestSnapshotEnums(unittest.TestCase):
    """Verify enum values are stable — downstream code may depend on them."""

    def test_snap_edit_type_values(self):
        self.assertEqual(SnapEditType.ADD_DIR.value, "Add")
        self.assertEqual(SnapEditType.REMOVE_DIR.value, "Remove")

    def test_backup_type_values(self):
        self.assertEqual(BackupType.ASSOCIATED_DIRECTORIES.value, 1)
        self.assertEqual(BackupType.SNAPSHOT_DIRECTORY.value, 2)

    def test_snapshot_sort_key_values(self):
        self.assertEqual(SnapshotSortKey.NAME.value, "name")
        self.assertEqual(SnapshotSortKey.DATE_CREATED.value, "date_created")
        self.assertEqual(SnapshotSortKey.ASSOC_DIR_MB_SIZE.value, "get_assoc_dir_mb_size")


class TestSnapEditAction(unittest.TestCase):
    """Tests for SnapEditAction — especially BUG-1 timestamp uniqueness."""

    def test_bug1_timestamp_unique_per_instance(self):
        """BUG-1: timestamp must not be a shared mutable default."""
        e1 = SnapEditAction(action_type=SnapEditType.ADD_DIR)
        time.sleep(0.01)
        e2 = SnapEditAction(action_type=SnapEditType.ADD_DIR)
        self.assertLessEqual(e1.timestamp, e2.timestamp)
        self.assertIsNot(e1.timestamp, e2.timestamp)

    def test_fields_default_to_empty_string(self):
        e = SnapEditAction(action_type=SnapEditType.REMOVE_DIR)
        self.assertEqual(e.new_path, "")
        self.assertEqual(e.folder_id_to_remove, "")
        self.assertEqual(e.directory_name_to_remove, "")


class TestSnapshotSettings(unittest.TestCase):
    """Tests for SnapshotSettings defaults and backup-enabled guards."""

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

    def test_backup_enabled_requires_both_flag_and_path(self):
        self.assertFalse(SnapshotSettings(backup_pre_install=True, backup_path=None).bck_before_install_enabled)
        self.assertFalse(SnapshotSettings(backup_pre_install=False, backup_path=Path("/tmp")).bck_before_install_enabled)
        self.assertTrue(SnapshotSettings(backup_pre_install=True, backup_path=Path("/tmp")).bck_before_install_enabled)
        self.assertTrue(SnapshotSettings(backup_pre_modify=True, backup_path=Path("/tmp")).bck_before_modify_enabled)
        self.assertTrue(SnapshotSettings(backup_pre_delete=True, backup_path=Path("/tmp")).bck_before_delete_enabled)


class TestSnapshotModel(unittest.TestCase):
    """Tests for the Snapshot dataclass: properties, data CRUD, clone."""

    def setUp(self):
        setup_test_dirs()
        create_source_dirs(SOURCE_DATA_PATH, ["d1", "d2", "d3"])

    def tearDown(self):
        teardown_test_dirs()

    # --- BUG-1 regression ---

    def test_bug1_date_created_unique_per_instance(self):
        s1 = Snapshot(id="a", name="A", desc="")
        time.sleep(0.01)
        s2 = Snapshot(id="b", name="B", desc="")
        self.assertLessEqual(s1.date_created, s2.date_created)
        self.assertIsNot(s1.date_created, s2.date_created)

    # --- Properties ---

    def test_folder_name_equals_id(self):
        snap = Snapshot(id="snap_id_123", name="X", desc="")
        self.assertEqual(snap.folder_name, "snap_id_123")

    def test_tags_as_string_sorted(self):
        snap = Snapshot(id="1", name="T", desc="", tags=["gamma", "alpha", "beta"])
        self.assertEqual(snap.tags_as_string, "alpha, beta, gamma")

    def test_tags_as_string_empty_returns_space(self):
        snap = Snapshot(id="2", name="T", desc="", tags=[])
        self.assertEqual(snap.tags_as_string, " ")

    def test_tags_as_string_single_tag(self):
        snap = Snapshot(id="3", name="T", desc="", tags=["solo"])
        self.assertEqual(snap.tags_as_string, "solo")

    def test_get_assoc_dir_mb_size_sums_directories(self):
        src = create_source_dirs(SOURCE_DATA_PATH, ["sz1", "sz2"])
        snap = make_snapshot("SizeSnap", src, n=2)
        total = snap.get_assoc_dir_mb_size
        self.assertGreaterEqual(total, 0.0)
        self.assertEqual(total, sum(d.mb_size for d in snap.directories if d.mb_size is not None))

    # --- get_for_table_array ---

    def test_get_for_table_array_structure(self):
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

    # --- Data dictionary CRUD ---

    def test_add_get_has_edit_remove_data_item(self):
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

    def test_clear_all_data_removes_all_entries(self):
        snap = Snapshot(id="1", name="T", desc="")
        snap.add_data_item("a", "1")
        snap.add_data_item("b", "2")
        snap.clear_all_data()
        self.assertEqual(len(snap.data), 0)

    def test_get_data_item_returns_default_when_missing(self):
        snap = Snapshot(id="1", name="T", desc="")
        self.assertEqual(snap.get_data_item("missing", default="fallback"), "fallback")
        self.assertEqual(snap.get_data_item("missing"), "")

    # --- clone() deep-copy ---

    def test_clone_is_independent_deep_copy(self):
        src = create_source_dirs(SOURCE_DATA_PATH, ["cl1"])
        snap1 = make_snapshot("Original", src, n=1)
        snap1.add_data_item("key", "value")
        snap1.tags.append("extra")

        snap2 = snap1.clone()

        self.assertIsNot(snap1, snap2)
        self.assertEqual(snap1.id, snap2.id)

        # Mutating the clone must not affect the original
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


if __name__ == "__main__":
    unittest.main()
