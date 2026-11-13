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

import time
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

from pylizlib.core.os.snap.copy_strategy import CopyMetadataMode, ExtendedMetadataCopyStrategy, SequentialFileCopyStrategy, VerifiedFileCopyStrategy
from pylizlib.core.os.snap.domain import (
    BackupType,
    SnapDirAssociation,
    SnapEditAction,
    SnapEditType,
    Snapshot,
    SnapshotSettings,
    SnapshotSortKey,
)
from test.support.snapshot import (
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

    def test_directory_name_is_stable_and_independent_of_presentation_fields(self):
        d = SOURCE_DATA_PATH / "mydir"
        d.mkdir()
        assoc = SnapDirAssociation(index=5, original_path=str(d), folder_id="abc")
        stored_name = assoc.directory_name
        assoc.index = 1
        assoc.original_path = "/a/different-basename"
        self.assertEqual(assoc.directory_name, stored_name)
        self.assertNotEqual(SnapDirAssociation(index=1, original_path=str(d), folder_id="different-id").directory_name, stored_name)

    def test_original_path_normalised_to_posix(self):
        d = SOURCE_DATA_PATH / "normdir"
        d.mkdir()
        assoc = SnapDirAssociation(index=1, original_path=str(d), folder_id="x")
        self.assertEqual(assoc.original_path, d.as_posix())

    def test_mb_size_remains_unknown_until_content_is_captured(self):
        d = SOURCE_DATA_PATH / "sizeddir"
        d.mkdir()
        (d / "bigfile.txt").write_text("x" * 10_000, encoding="utf-8")
        assoc = SnapDirAssociation(index=1, original_path=str(d), folder_id="sz")
        self.assertIsNone(assoc.mb_size)

    def test_missing_source_does_not_masquerade_as_a_zero_byte_capture(self):
        assoc = SnapDirAssociation(
            index=1,
            original_path=str(SOURCE_DATA_PATH / "ghost_dir"),
            folder_id="g",
        )
        self.assertIsNone(assoc.mb_size)

    def test_association_construction_does_not_walk_a_remote_source(self):
        with patch("os.walk", side_effect=AssertionError("source tree was scanned")) as walk:
            assoc = SnapDirAssociation(index=1, original_path="/remote/share/data", folder_id="remote")
        walk.assert_not_called()
        self.assertIsNone(assoc.mb_size)

    def test_mb_size_preserved_when_explicitly_provided(self):
        d = SOURCE_DATA_PATH / "preserved"
        d.mkdir()
        assoc = SnapDirAssociation(index=1, original_path=str(d), folder_id="p", mb_size=42.0)
        self.assertEqual(assoc.mb_size, 42.0)

    def test_manifest_size_overrides_a_stale_association_estimate(self):
        assoc = SnapDirAssociation(
            index=1,
            original_path="/source",
            folder_id="captured-size",
            mb_size=42.0,
            integrity_manifest={
                ".": {"type": "directory", "size": 0, "sha256": None},
                "value": {"type": "file", "size": 1_048_576, "sha256": "a" * 64},
            },
        )

        self.assertEqual(assoc.mb_size, 1.0)

    def test_capture_interval_requires_timezone_and_ordered_timestamps(self):
        from datetime import datetime, timezone

        with self.assertRaisesRegex(ValueError, "explicit timezone"):
            Snapshot("naive-capture", "naive", "", capture_started_at=datetime(2026, 1, 1))

        with self.assertRaisesRegex(ValueError, "cannot precede"):
            Snapshot(
                "reversed-capture",
                "reversed",
                "",
                capture_started_at=datetime(2026, 1, 1, 0, 0, 1, tzinfo=timezone.utc),
                capture_completed_at=datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
            )

    def test_next_index_increments(self):
        reset_index()
        i1 = SnapDirAssociation.next_index()
        i2 = SnapDirAssociation.next_index()
        self.assertEqual(i2, i1 + 1)

    def test_index_must_be_an_integer_before_it_can_name_a_directory(self):
        with self.assertRaises(TypeError):
            SnapDirAssociation(index="../../escape", original_path="/source", folder_id="bad-index")

        with self.assertRaises(TypeError):
            SnapDirAssociation(index=True, original_path="/source", folder_id="bool-index")

    def test_mutated_index_is_revalidated_when_directory_name_is_used(self):
        assoc = SnapDirAssociation(index=1, original_path="/source", folder_id="mutable-index", mb_size=0)
        assoc.index = "../../escape"
        with self.assertRaises(TypeError):
            _ = assoc.directory_name

    def test_integrity_manifest_rejects_paths_outside_association(self):
        with self.assertRaises(ValueError):
            SnapDirAssociation(
                index=1,
                original_path="/source",
                folder_id="manifest-path",
                integrity_manifest={
                    ".": {"type": "directory", "size": 0, "sha256": None},
                    "../outside.txt": {"type": "file", "size": 1, "sha256": "0" * 64},
                },
            )


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

    def test_path_traversal_names_are_rejected(self):
        with self.assertRaises(ValueError):
            SnapEditAction(action_type=SnapEditType.REMOVE_DIR, directory_name_to_remove="../../outside")


class TestSnapshotSettings(unittest.TestCase):
    """Tests for SnapshotSettings defaults and backup-enabled guards."""

    def test_defaults(self):
        s = SnapshotSettings()
        self.assertEqual(s.json_filename, "snapshot.json")
        self.assertIsNone(s.backup_path)
        self.assertFalse(s.backup_pre_install)
        self.assertFalse(s.backup_pre_modify)
        self.assertFalse(s.backup_pre_delete)
        self.assertFalse(s.install_with_everyone_full_control)
        self.assertEqual(s.snap_id_length, 20)
        self.assertEqual(s.folder_id_length, 6)
        self.assertIsInstance(s.copy_strategy, SequentialFileCopyStrategy)
        self.assertIs(s.copy_metadata_mode, CopyMetadataMode.BASIC)
        self.assertFalse(s.allow_unverified_legacy_snapshots)
        self.assertIsNone(s.archive_temp_directory)
        self.assertEqual(s.max_archive_uncompressed_bytes, 100 * 1024 * 1024 * 1024)
        self.assertEqual(s.max_archive_entries, 1_000_000)

    def test_extended_metadata_setting_decorates_the_selected_copy_strategy(self):
        settings = SnapshotSettings(copy_metadata_mode=CopyMetadataMode.EXTENDED)

        self.assertIsInstance(settings.copy_strategy, ExtendedMetadataCopyStrategy)
        self.assertIsInstance(settings.copy_strategy.delegate, SequentialFileCopyStrategy)

    def test_metadata_mode_can_be_changed_after_settings_are_created(self):
        settings = SnapshotSettings()
        original_strategy = settings.copy_strategy

        settings.copy_metadata_mode = CopyMetadataMode.EXTENDED
        self.assertIsInstance(settings.copy_strategy, ExtendedMetadataCopyStrategy)
        settings.copy_metadata_mode = CopyMetadataMode.BASIC

        self.assertIs(settings.copy_strategy, original_strategy)

    def test_copy_metadata_mode_must_be_an_enum_value(self):
        with self.assertRaises(TypeError):
            SnapshotSettings(copy_metadata_mode="extended")

    def test_legacy_integrity_override_must_be_a_boolean(self):
        with self.assertRaises(TypeError):
            SnapshotSettings(allow_unverified_legacy_snapshots=1)

    def test_archive_limits_and_temporary_directory_are_validated(self):
        with self.assertRaises(TypeError):
            SnapshotSettings(max_archive_entries=True)
        with self.assertRaises(ValueError):
            SnapshotSettings(max_archive_uncompressed_bytes=-1)
        with self.assertRaises(TypeError):
            SnapshotSettings(archive_temp_directory="/tmp")

        settings = SnapshotSettings(archive_temp_directory=Path("/archive-staging"), max_archive_entries=None)
        self.assertEqual(settings.archive_temp_directory, Path("/archive-staging"))
        self.assertIsNone(settings.max_archive_entries)

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

    def test_snapshot_id_must_be_a_single_path_component(self):
        with self.assertRaises(ValueError):
            Snapshot(id="../../escape", name="Invalid", desc="")

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


def test_runtime_selection_avoids_double_wrapping_and_preserves_explicit_wrappers():
    """Mode transitions differ from assigning an explicit wrapper while already BASIC."""
    first = SequentialFileCopyStrategy()
    second = VerifiedFileCopyStrategy()
    settings = SnapshotSettings(copy_strategy=first)
    settings.copy_metadata_mode = CopyMetadataMode.EXTENDED
    wrapper = settings.copy_strategy
    assert wrapper.delegate is first
    settings.copy_metadata_mode = CopyMetadataMode.EXTENDED
    assert settings.copy_strategy is wrapper
    settings.copy_strategy = second
    assert settings.copy_strategy.delegate is second
    settings.copy_metadata_mode = CopyMetadataMode.BASIC
    assert settings.copy_strategy is second

    explicit = ExtendedMetadataCopyStrategy(first)
    settings.copy_strategy = explicit
    settings.copy_metadata_mode = CopyMetadataMode.BASIC
    assert settings.copy_strategy is explicit
    settings.copy_metadata_mode = CopyMetadataMode.EXTENDED
    assert settings.copy_strategy is explicit
    settings.copy_metadata_mode = CopyMetadataMode.BASIC
    assert settings.copy_strategy is first
    with pytest.raises(TypeError, match="must be a CopyMetadataMode"):
        settings.copy_metadata_mode = "extended"
    assert settings.copy_metadata_mode is CopyMetadataMode.BASIC
    assert settings.copy_strategy is first


if __name__ == "__main__":
    unittest.main()
