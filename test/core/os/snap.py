import unittest
from unittest.mock import patch
from pathlib import Path
import shutil
import zipfile
from datetime import datetime, timedelta

from pylizlib.core.os.snap import (
    Snapshot,
    SnapshotCatalogue,
    SnapshotManager,
    SnapshotSettings,
    SnapDirAssociation,
    SnapshotUtils,
    SnapEditType,
    SnapshotSerializer,
    SnapshotSearcher,
    SnapshotSearchResult,
    SnapshotSortKey,
    SnapshotSearchType,
    SnapshotSearchParams,
)
from pylizlib.core.data.gen import gen_random_string

# Define test directories
TEST_ROOT = Path(__file__).parent.parent.parent
TEST_LOCAL_ROOT = TEST_ROOT.joinpath("test_local")
CATALOGUE_PATH = TEST_LOCAL_ROOT / "snapshots"
SOURCE_DATA_PATH = TEST_LOCAL_ROOT / "source_data"
INSTALL_DEST_PATH = TEST_LOCAL_ROOT / "install_dest"
BACKUP_PATH = TEST_LOCAL_ROOT / "backups"


def create_test_snapshot(name: str, num_dirs: int = 2) -> Snapshot:
    """Helper to create a snapshot for testing."""
    SnapDirAssociation._current_index = 0  # Reset index for predictability
    dirs = []
    # Ensure consistent order for tests
    source_dirs = sorted([d for d in SOURCE_DATA_PATH.iterdir() if d.is_dir()])
    for i in range(min(num_dirs, len(source_dirs))):
        dirs.append(
            SnapDirAssociation(
                index=SnapDirAssociation.next_index(),
                original_path=str(source_dirs[i]),
                folder_id=gen_random_string(6),
            )
        )
    return Snapshot(
        id=gen_random_string(10),
        name=name,
        desc=f"Description for {name}",
        directories=dirs,
        author="TestRunner"
    )


class TestSnapshot(unittest.TestCase):
    def setUp(self):
        """Set up for each test method."""
        if TEST_LOCAL_ROOT.exists():
            shutil.rmtree(TEST_LOCAL_ROOT)
        SOURCE_DATA_PATH.mkdir(parents=True, exist_ok=True)
        (SOURCE_DATA_PATH / "dir1").mkdir()

    def tearDown(self):
        """Tear down after each test method."""
        shutil.rmtree(TEST_LOCAL_ROOT)

    def test_data_methods(self):
        snap = Snapshot(id="1", name="test", desc="d")
        self.assertFalse(snap.has_data_item("key1"))

        snap.add_data_item("key1", "value1")
        self.assertTrue(snap.has_data_item("key1"))
        self.assertEqual(snap.get_data_item("key1"), "value1")

        snap.edit_data_item("key1", "value2")
        self.assertEqual(snap.get_data_item("key1"), "value2")

        with self.assertRaises(KeyError):
            snap.edit_data_item("nonexistent", "value")

        removed_value = snap.remove_data_item("key1")
        self.assertEqual(removed_value, "value2")
        self.assertFalse(snap.has_data_item("key1"))

        snap.add_data_item("key2", "value2")
        snap.clear_all_data()
        self.assertEqual(len(snap.data), 0)

    def test_clone(self):
        snap1 = create_test_snapshot("CloneTest")
        snap1.add_data_item("key", "value")

        snap2 = snap1.clone()

        self.assertIsNot(snap1, snap2)
        self.assertEqual(snap1.id, snap2.id)
        self.assertEqual(snap1.name, snap2.name)

        # Check deep copy of lists and dicts
        self.assertIsNot(snap1.directories, snap2.directories)
        self.assertIsNot(snap1.tags, snap2.tags)
        self.assertIsNot(snap1.data, snap2.data)
        self.assertEqual(snap1.data, snap2.data)

        snap2.name = "Cloned"
        snap2.tags.append("cloned_tag")
        snap2.data["key"] = "new_value"

        self.assertNotEqual(snap1.name, snap2.name)
        self.assertNotEqual(snap1.tags, snap2.tags)
        self.assertNotEqual(snap1.data, snap2.data)


class TestSnapshotUtils(unittest.TestCase):
    def setUp(self):
        if TEST_LOCAL_ROOT.exists():
            shutil.rmtree(TEST_LOCAL_ROOT)
        SOURCE_DATA_PATH.mkdir(parents=True, exist_ok=True)
        (SOURCE_DATA_PATH / "dir1").mkdir()
        (SOURCE_DATA_PATH / "dir2").mkdir()
        (SOURCE_DATA_PATH / "dir3").mkdir()

    def tearDown(self):
        shutil.rmtree(TEST_LOCAL_ROOT)

    def test_get_edits_between_snapshots(self):
        snap_old = create_test_snapshot("Old", num_dirs=2)
        snap_new = snap_old.clone()

        # Test no changes
        edits_none = SnapshotUtils.get_edits_between_snapshots(snap_old, snap_new)
        self.assertEqual(len(edits_none), 0)

        # Test addition
        dir3_path = str(SOURCE_DATA_PATH / "dir3")
        snap_new.directories.append(SnapDirAssociation(index=3, original_path=dir3_path, folder_id="id3"))

        edits_add = SnapshotUtils.get_edits_between_snapshots(snap_old, snap_new)
        self.assertEqual(len(edits_add), 1)
        self.assertEqual(edits_add[0].action_type, SnapEditType.ADD_DIR)
        self.assertEqual(Path(edits_add[0].new_path).as_posix(), Path(dir3_path).as_posix())

        # Test removal
        snap_new_remove = snap_old.clone()
        removed_assoc = snap_new_remove.directories.pop(0)

        edits_remove = SnapshotUtils.get_edits_between_snapshots(snap_old, snap_new_remove)
        self.assertEqual(len(edits_remove), 1)
        self.assertEqual(edits_remove[0].action_type, SnapEditType.REMOVE_DIR)
        self.assertEqual(edits_remove[0].folder_id_to_remove, removed_assoc.folder_id)
        self.assertEqual(edits_remove[0].directory_name_to_remove, removed_assoc.directory_name)

    def test_sort_snapshots(self):
        now = datetime.now()
        s1 = Snapshot(id="1", name="Beta", desc="d", date_created=now - timedelta(days=1), date_modified=now)
        s2 = Snapshot(id="2", name="alpha", desc="d", date_created=now - timedelta(days=2), date_modified=None)
        s3 = Snapshot(id="3", name="Gamma", desc="d", date_created=now, date_modified=now - timedelta(days=1))

        snapshots = [s1, s2, s3]

        # Test sort by name (ascending, case-insensitive)
        sorted_by_name = SnapshotUtils.sort_snapshots(snapshots, SnapshotSortKey.NAME)
        self.assertEqual([s.name for s in sorted_by_name], ["alpha", "Beta", "Gamma"])

        # Test sort by name (descending, case-insensitive)
        sorted_by_name_desc = SnapshotUtils.sort_snapshots(snapshots, SnapshotSortKey.NAME, reverse=True)
        self.assertEqual([s.name for s in sorted_by_name_desc], ["Gamma", "Beta", "alpha"])

        # Test sort by date_created (ascending)
        sorted_by_date = SnapshotUtils.sort_snapshots(snapshots, SnapshotSortKey.DATE_CREATED)
        self.assertEqual([s.id for s in sorted_by_date], ["2", "1", "3"])

        # Test sort by date_created (descending)
        sorted_by_date_desc = SnapshotUtils.sort_snapshots(snapshots, SnapshotSortKey.DATE_CREATED, reverse=True)
        self.assertEqual([s.id for s in sorted_by_date_desc], ["3", "1", "2"])

        # Test sort by date_modified (with None, ascending)
        sorted_with_none = SnapshotUtils.sort_snapshots(snapshots, SnapshotSortKey.DATE_MODIFIED)
        self.assertEqual([s.id for s in sorted_with_none], ["3", "1", "2"])

        # Test sort by date_modified (with None, descending)
        sorted_with_none_desc = SnapshotUtils.sort_snapshots(snapshots, SnapshotSortKey.DATE_MODIFIED, reverse=True)
        self.assertEqual([s.id for s in sorted_with_none_desc], ["1", "3", "2"])

        # Test sort by ASSOC_DIR_MB_SIZE
        # Create snapshots with different sizes
        # Ensure directories have some content for size calculation
        (SOURCE_DATA_PATH / "dir1" / "file_s.txt").write_text("s" * 100) # ~0.1KB
        (SOURCE_DATA_PATH / "dir2" / "file_m.txt").write_text("m" * 1000) # ~1KB
        (SOURCE_DATA_PATH / "dir3" / "file_l.txt").write_text("l" * 10000) # ~10KB

        # Re-create snapshots to ensure mb_size is calculated based on new file sizes
        snap_small = create_test_snapshot("SmallSnap", num_dirs=1) # Uses dir1
        snap_medium = create_test_snapshot("MediumSnap", num_dirs=2) # Uses dir1, dir2
        snap_large = create_test_snapshot("LargeSnap", num_dirs=3) # Uses dir1, dir2, dir3

        # Ensure mb_size is calculated and ordered correctly
        self.assertGreater(snap_small.get_assoc_dir_mb_size, 0)
        self.assertGreater(snap_medium.get_assoc_dir_mb_size, snap_small.get_assoc_dir_mb_size)
        self.assertGreater(snap_large.get_assoc_dir_mb_size, snap_medium.get_assoc_dir_mb_size)

        snapshots_for_size_sort = [snap_large, snap_small, snap_medium]

        sorted_by_size = SnapshotUtils.sort_snapshots(snapshots_for_size_sort, SnapshotSortKey.ASSOC_DIR_MB_SIZE)
        self.assertEqual([s.name for s in sorted_by_size], ["SmallSnap", "MediumSnap", "LargeSnap"])

        sorted_by_size_desc = SnapshotUtils.sort_snapshots(snapshots_for_size_sort, SnapshotSortKey.ASSOC_DIR_MB_SIZE, reverse=True)
        self.assertEqual([s.name for s in sorted_by_size_desc], ["LargeSnap", "MediumSnap", "SmallSnap"])


class TestSnapshotManager(unittest.TestCase):

    def setUp(self):
        """Set up for each test method."""
        if TEST_LOCAL_ROOT.exists():
            shutil.rmtree(TEST_LOCAL_ROOT)

        CATALOGUE_PATH.mkdir(parents=True, exist_ok=True)
        SOURCE_DATA_PATH.mkdir(parents=True, exist_ok=True)

        (SOURCE_DATA_PATH / "dir1").mkdir()
        (SOURCE_DATA_PATH / "dir1" / "file1.txt").write_text("content1")
        (SOURCE_DATA_PATH / "dir2").mkdir()
        (SOURCE_DATA_PATH / "dir2" / "file2.txt").write_text("content2")

        self.snap = create_test_snapshot("ManagerTestSnap")
        self.manager = SnapshotManager(self.snap, CATALOGUE_PATH)

    def tearDown(self):
        """Tear down after each test method."""
        shutil.rmtree(TEST_LOCAL_ROOT)

    def test_create_and_delete(self):
        self.assertFalse(self.manager.path_snapshot.exists())

        self.manager.create()

        self.assertTrue(self.manager.path_snapshot.exists())
        self.assertTrue(self.manager.path_snapshot_json.exists())

        # Check copied directories
        snap_dir_path = self.manager.path_snapshot
        dir1_in_snap = snap_dir_path / self.snap.directories[0].directory_name
        self.assertTrue(dir1_in_snap.exists())
        self.assertTrue((dir1_in_snap / "file1.txt").exists())

        self.manager.delete()
        self.assertFalse(self.manager.path_snapshot.exists())

    def test_update_json_fields(self):
        self.manager.create()

        # Test base fields update
        self.snap.name = "New Name"
        self.snap.tags = ["new", "tag"]
        self.manager.update_json_base_fields()

        reloaded_snap = SnapshotSerializer.from_json(self.manager.path_snapshot_json)
        self.assertEqual(reloaded_snap.name, "New Name")
        self.assertEqual(reloaded_snap.tags, ["new", "tag"])
        self.assertIsNotNone(reloaded_snap.date_modified)

        # Test data fields update
        self.snap.data["mykey"] = "myvalue"
        self.manager.update_json_data_fields()

        reloaded_snap_2 = SnapshotSerializer.from_json(self.manager.path_snapshot_json)
        self.assertEqual(reloaded_snap_2.get_data_item("mykey"), "myvalue")
        self.assertIsNotNone(reloaded_snap_2.date_last_modified)

    def test_install_and_uninstall_directory(self):
        self.manager.create()

        # Install a new directory
        new_dir_path = SOURCE_DATA_PATH / "dir_to_install"
        new_dir_path.mkdir()
        (new_dir_path / "install_file.txt").write_text("installed")

        self.manager.install_directory(new_dir_path)

        self.assertEqual(len(self.snap.directories), 3)
        installed_dir_assoc = self.snap.directories[-1]
        self.assertEqual(Path(installed_dir_assoc.original_path).as_posix(), new_dir_path.as_posix())

        path_in_snap = self.manager.path_snapshot / installed_dir_assoc.directory_name
        self.assertTrue(path_in_snap.exists())
        self.assertTrue((path_in_snap / "install_file.txt").exists())

        # Uninstall the directory
        folder_id_to_remove = installed_dir_assoc.folder_id
        self.manager.uninstall_directory_by_folder_id(folder_id_to_remove)

        self.assertEqual(len(self.snap.directories), 2)
        self.assertFalse(path_in_snap.exists())


class TestSnapshotCatalogue(unittest.TestCase):

    def setUp(self):
        """Set up for each test method."""
        if TEST_LOCAL_ROOT.exists():
            shutil.rmtree(TEST_LOCAL_ROOT)

        CATALOGUE_PATH.mkdir(parents=True, exist_ok=True)
        SOURCE_DATA_PATH.mkdir(parents=True, exist_ok=True)
        INSTALL_DEST_PATH.mkdir(parents=True, exist_ok=True)
        BACKUP_PATH.mkdir(parents=True, exist_ok=True)

        (SOURCE_DATA_PATH / "dir1").mkdir()
        (SOURCE_DATA_PATH / "dir1" / "file1.txt").write_text("content1")
        (SOURCE_DATA_PATH / "dir2").mkdir()
        (SOURCE_DATA_PATH / "dir2" / "file2.txt").write_text("content2")
        (SOURCE_DATA_PATH / "dir3").mkdir()
        (SOURCE_DATA_PATH / "dir3" / "subdir").mkdir()
        (SOURCE_DATA_PATH / "dir3" / "subdir" / "file3.txt").write_text("content3")

        self.settings = SnapshotSettings(
            backup_path=BACKUP_PATH,
            backup_pre_delete=True,
            backup_pre_install=True,
            backup_pre_modify=True
        )
        self.catalogue = SnapshotCatalogue(CATALOGUE_PATH, settings=self.settings)

    def tearDown(self):
        """Tear down after each test method."""
        shutil.rmtree(TEST_LOCAL_ROOT)

    def test_add_and_get_all_and_get_by_id(self):
        self.assertEqual(len(self.catalogue.get_all()), 0)

        snap1 = create_test_snapshot("Snap1")
        self.catalogue.add(snap1)

        all_snaps = self.catalogue.get_all()
        self.assertEqual(len(all_snaps), 1)
        self.assertEqual(all_snaps[0].id, snap1.id)
        self.assertTrue((CATALOGUE_PATH / snap1.id).exists())
        self.assertTrue((CATALOGUE_PATH / snap1.id / self.settings.json_filename).exists())

        retrieved_snap = self.catalogue.get_by_id(snap1.id)
        self.assertIsNotNone(retrieved_snap)
        self.assertEqual(retrieved_snap.name, snap1.name)

        self.assertIsNone(self.catalogue.get_by_id("non-existent-id"))

    def test_delete(self):
        snap1 = create_test_snapshot("Snap1ToDelete")
        self.catalogue.add(snap1)
        self.assertTrue(self.catalogue.exists(snap1.id))

        self.catalogue.delete(snap1)

        self.assertFalse(self.catalogue.exists(snap1.id))
        self.assertFalse((CATALOGUE_PATH / snap1.id).exists())

        # Check if backup was created
        self.assertTrue(any(f.name.startswith(f"backup_beforeDelete_{snap1.id}_sd") for f in BACKUP_PATH.iterdir()))

    def test_update_snapshot(self):
        snap_old = create_test_snapshot("OriginalSnap", num_dirs=2)
        self.catalogue.add(snap_old)

        # Clone and modify
        snap_new = snap_old.clone()
        snap_new.name = "UpdatedSnap"
        snap_new.desc = "Updated Description"
        # Remove one dir and add another
        snap_new.directories.pop(0)
        new_dir_path = str(SOURCE_DATA_PATH / "dir3")
        snap_new.directories.append(
            SnapDirAssociation(index=3, original_path=new_dir_path, folder_id=gen_random_string(6)))

        self.catalogue.update_snapshot_by_objs(snap_old, snap_new)

        updated_snap_from_cat = self.catalogue.get_by_id(snap_new.id)
        self.assertEqual(updated_snap_from_cat.name, "UpdatedSnap")
        self.assertEqual(len(updated_snap_from_cat.directories), 2)

        original_paths = {d.original_path for d in updated_snap_from_cat.directories}
        self.assertIn(Path(new_dir_path).as_posix(), original_paths)
        self.assertNotIn(Path(snap_old.directories[0].original_path).as_posix(), original_paths)

        # Check backup
        self.assertTrue(any(f.name.startswith(f"backup_beforeEdit_{snap_new.id}_sd") for f in BACKUP_PATH.iterdir()))

        # Check snapshot directory content
        snap_dir = CATALOGUE_PATH / snap_new.id
        dir_names_in_snap = {d.name for d in snap_dir.iterdir() if d.is_dir()}

        removed_dir_name = snap_old.directories[0].directory_name
        self.assertNotIn(removed_dir_name, dir_names_in_snap)

        added_dir_name = snap_new.directories[-1].directory_name
        self.assertIn(added_dir_name, dir_names_in_snap)

    def test_duplicate_by_id(self):
        snap1 = create_test_snapshot("SnapToDuplicate")
        self.catalogue.add(snap1)

        self.catalogue.duplicate_by_id(snap1.id)

        all_snaps = self.catalogue.get_all()
        self.assertEqual(len(all_snaps), 2)

        original_snap = self.catalogue.get_by_id(snap1.id)
        duplicated_snap = next((s for s in all_snaps if s.id != snap1.id), None)

        self.assertIsNotNone(duplicated_snap)
        self.assertEqual(duplicated_snap.name, original_snap.name + " Copy")
        self.assertNotEqual(duplicated_snap.id, original_snap.id)
        self.assertEqual(len(duplicated_snap.directories), len(original_snap.directories))

    def test_install(self):
        snap1 = create_test_snapshot("SnapToInstall", num_dirs=1)
        self.catalogue.add(snap1)

        install_target = Path(snap1.directories[0].original_path)

        # Modify the target before install to check if it gets cleaned
        (install_target / "extra_file.txt").write_text("this should be deleted")

        self.catalogue.install(snap1)

        # Check if target is cleaned and has the correct content
        self.assertFalse((install_target / "extra_file.txt").exists())
        self.assertTrue((install_target / "file1.txt").exists())
        self.assertEqual((install_target / "file1.txt").read_text(), "content1")

        # Check backup
        self.assertTrue(any(f.name.startswith(f"backup_preinstall_{snap1.id}_ad") for f in BACKUP_PATH.iterdir()))

        # Check last used date
        updated_snap = self.catalogue.get_by_id(snap1.id)
        self.assertIsNotNone(updated_snap.date_last_used)

    def test_remove_installed_copies(self):
        # Setup: Create a snapshot and install it
        snap_to_remove = create_test_snapshot("SnapToRemove", num_dirs=2)

        # Ensure the original_path for the snapshot directories are within INSTALL_DEST_PATH
        # This is crucial to avoid deleting actual source data.
        # We'll create dummy directories in INSTALL_DEST_PATH for this test.
        install_dir_1_path = INSTALL_DEST_PATH / "snap_dir_1_test"
        install_dir_2_path = INSTALL_DEST_PATH / "snap_dir_2_test"

        # Create these directories and some content
        install_dir_1_path.mkdir(parents=True, exist_ok=True)
        (install_dir_1_path / "file_a.txt").write_text("content A")
        install_dir_2_path.mkdir(parents=True, exist_ok=True)
        (install_dir_2_path / "file_b.txt").write_text("content B")

        # Update the snapshot's directories to point to these test install paths
        snap_to_remove.directories = [
            SnapDirAssociation(index=1, original_path=str(install_dir_1_path), folder_id="id1"),
            SnapDirAssociation(index=2, original_path=str(install_dir_2_path), folder_id="id2"),
        ]

        self.catalogue.add(snap_to_remove) # Adds to catalogue
        self.catalogue.install(snap_to_remove) # Installs to original_path locations

        # Verify they exist before removal
        self.assertTrue(install_dir_1_path.exists())
        self.assertTrue(install_dir_2_path.exists())
        self.assertTrue((install_dir_1_path / "file_a.txt").exists())

        # Test Case 1: Successful Removal
        self.catalogue.remove_installed_copies(snap_to_remove.id)

        self.assertFalse(install_dir_1_path.exists())
        self.assertFalse(install_dir_2_path.exists())

        # Test Case 2: Snapshot Not Found (should log a warning)
        with patch('pylizlib.core.log.pylizLogger.logger.warning') as mock_warning:
            self.catalogue.remove_installed_copies("non-existent-id")
            mock_warning.assert_called_once_with("Snapshot with ID 'non-existent-id' not found. Cannot remove installed copies.")

        # Test Case 3: Some Directories Missing (should not raise error)
        snap_partial_remove = create_test_snapshot("SnapPartialRemove", num_dirs=1)
        install_dir_3_path = INSTALL_DEST_PATH / "snap_dir_3_test"
        install_dir_4_path = INSTALL_DEST_PATH / "snap_dir_4_test_missing"

        # Create both directories so 'add' succeeds
        install_dir_3_path.mkdir(parents=True, exist_ok=True)
        (install_dir_3_path / "file_c.txt").write_text("content C")
        install_dir_4_path.mkdir(parents=True, exist_ok=True) # Create this one too
        (install_dir_4_path / "file_d.txt").write_text("content D") # Add some content

        snap_partial_remove.directories = [
            SnapDirAssociation(index=1, original_path=str(install_dir_3_path), folder_id="id3"),
            SnapDirAssociation(index=2, original_path=str(install_dir_4_path), folder_id="id4"),
        ]
        self.catalogue.add(snap_partial_remove) # This will now succeed

        # Now, simulate one of the installed copies being missing
        shutil.rmtree(install_dir_4_path) # Manually delete it

        self.assertTrue(install_dir_3_path.exists())
        self.assertFalse(install_dir_4_path.exists()) # Confirm it's missing

        self.catalogue.remove_installed_copies(snap_partial_remove.id)

        self.assertFalse(install_dir_3_path.exists()) # Should be removed
        self.assertFalse(install_dir_4_path.exists()) # Should still be missing, no error

    def test_export_assoc_dirs(self):
        # Setup: Create a snapshot with some associated directories
        snap1 = create_test_snapshot("SnapToExport", num_dirs=2)
        self.catalogue.add(snap1)

        export_destination = TEST_LOCAL_ROOT / "exports"
        export_destination.mkdir()

        # Call the export method
        self.catalogue.export_assoc_dirs(snap1.id, export_destination)

        # Verify the zip file was created
        self.assertTrue(export_destination.exists())
        export_files = list(export_destination.iterdir())
        self.assertEqual(len(export_files), 1)
        
        zip_file = export_files[0]
        self.assertTrue(zip_file.name.startswith(f"export_{snap1.id}_ad"))
        self.assertTrue(zip_file.name.endswith(".zip"))

        # Verify the contents of the zip file
        with zipfile.ZipFile(zip_file, 'r') as zf:
            zipped_files = zf.namelist()
            # zipfile uses forward slashes
            self.assertIn("dir1/file1.txt", zipped_files)
            self.assertIn("dir2/file2.txt", zipped_files)

    def test_export_snapshot(self):
        # Setup: Create a snapshot
        snap1 = create_test_snapshot("SnapToExportFull", num_dirs=2)
        self.catalogue.add(snap1)

        export_destination = TEST_LOCAL_ROOT / "exports_full"
        export_destination.mkdir()

        # Call the export method
        self.catalogue.export_snapshot(snap1.id, export_destination)

        # Verify the zip file was created
        self.assertTrue(export_destination.exists())
        export_files = list(export_destination.iterdir())
        self.assertEqual(len(export_files), 1)
        
        zip_file = export_files[0]
        self.assertTrue(zip_file.name.startswith(f"export_snap_{snap1.id}_sd"))
        self.assertTrue(zip_file.name.endswith(".zip"))

        # Verify the contents of the zip file
        with zipfile.ZipFile(zip_file, 'r') as zf:
            zipped_files = zf.namelist()
            # Check for the snapshot.json file and a file from one of the copied directories
            self.assertIn(self.settings.json_filename, zipped_files)
            
            # The structure inside the zip is relative to the snapshot directory
            # e.g., "1-dir1/file1.txt"
            dir1_in_snap_name = snap1.directories[0].directory_name
            expected_file = f"{dir1_in_snap_name}/file1.txt"
            self.assertIn(expected_file, zipped_files)

    def test_import_snapshot(self):
        # 1. Create a snapshot and export it to have a valid zip file
        snap_to_export = create_test_snapshot("SnapToImport", num_dirs=1)
        self.catalogue.add(snap_to_export)
        
        export_destination = TEST_LOCAL_ROOT / "exports_for_import"
        export_destination.mkdir()
        self.catalogue.export_snapshot(snap_to_export.id, export_destination)
        
        zip_files = list(export_destination.glob("*.zip"))
        self.assertEqual(len(zip_files), 1)
        zip_to_import = zip_files[0]

        # 2. Delete the original snapshot from the catalogue to ensure we are testing import
        self.catalogue.delete(snap_to_export)
        self.assertFalse(self.catalogue.exists(snap_to_export.id))

        # 3. Import the snapshot
        self.catalogue.import_snapshot(zip_to_import)

        # 4. Verify it was imported correctly
        self.assertTrue(self.catalogue.exists(snap_to_export.id))
        imported_snap = self.catalogue.get_by_id(snap_to_export.id)
        self.assertIsNotNone(imported_snap)
        self.assertEqual(imported_snap.name, "SnapToImport")
        self.assertEqual(len(imported_snap.directories), 1)

        # 5. Test importing a duplicate ID
        with self.assertRaises(ValueError) as cm:
            self.catalogue.import_snapshot(zip_to_import)
        self.assertIn(f"A snapshot with the ID '{snap_to_export.id}' already exists", str(cm.exception))

        # 6. Test importing an invalid zip file (e.g., not a zip)
        invalid_zip_path = TEST_LOCAL_ROOT / "invalid.zip"
        invalid_zip_path.write_text("this is not a zip")
        with self.assertRaises(ValueError) as cm:
            self.catalogue.import_snapshot(invalid_zip_path)
        self.assertIn("is not a valid zip file", str(cm.exception))

        # 7. Test importing a zip file without a snapshot.json
        empty_zip_path = TEST_LOCAL_ROOT / "empty.zip"
        with zipfile.ZipFile(empty_zip_path, 'w') as zf:
            zf.writestr("test.txt", "hello")
        with self.assertRaises(ValueError) as cm:
            self.catalogue.import_snapshot(empty_zip_path)
        self.assertIn("does not contain a snapshot json file", str(cm.exception))


class TestSnapshotSearcher(unittest.TestCase):
    def setUp(self):
        """Set up for the searcher tests."""
        if TEST_LOCAL_ROOT.exists():
            shutil.rmtree(TEST_LOCAL_ROOT)

        CATALOGUE_PATH.mkdir(parents=True, exist_ok=True)
        SOURCE_DATA_PATH.mkdir(parents=True, exist_ok=True)

        # Create source files and content
        dir1 = SOURCE_DATA_PATH / "search_dir1"
        dir1.mkdir()
        (dir1 / "fileA.txt").write_text("Hello world\nThis is a test file.")
        (dir1 / "fileB.txt").write_text("Another file with test content.\nHello again.")

        dir2 = SOURCE_DATA_PATH / "search_dir2"
        dir2.mkdir()
        (dir2 / "fileC.log").write_text("Log file with some data: value=12345")
        (dir2 / "fileD.txt").write_text("No interesting content here.")

        # Create a binary file
        (dir2 / "binary.bin").write_bytes(b'\x80\x81\x82')

        # Create a snapshot containing these dirs
        SnapDirAssociation._current_index = 0
        self.snap = Snapshot(
            id="search-snap-id",
            name="SearchTestSnap",
            desc="A snapshot for testing search functionality",
            directories=[
                SnapDirAssociation(index=1, original_path=str(dir1), folder_id="d1"),
                SnapDirAssociation(index=2, original_path=str(dir2), folder_id="d2"),
            ],
            author="SearchTest"
        )

        self.catalogue = SnapshotCatalogue(CATALOGUE_PATH)
        self.catalogue.add(self.snap)
        self.searcher = SnapshotSearcher(self.catalogue)

    def tearDown(self):
        """Tear down after each test method."""
        shutil.rmtree(TEST_LOCAL_ROOT)

    def test_search_text_found(self):
        params = SnapshotSearchParams(
            query="Hello",
            search_type=SnapshotSearchType.TEXT
        )
        results = self.searcher.search(self.snap, params)
        self.assertEqual(len(results), 2)

        # Sort results to have a predictable order for assertions
        results.sort(key=lambda r: r.file_path)

        self.assertEqual("fileA.txt", results[0].file_path.name)
        self.assertEqual(results[0].line_number, 1)
        self.assertEqual(results[0].searched_text, "Hello")
        self.assertEqual(results[0].line_content, "Hello world")
        self.assertEqual(results[0].snapshot_name, self.snap.name)

        self.assertEqual("fileB.txt", results[1].file_path.name)
        self.assertEqual(results[1].line_number, 2)
        self.assertEqual(results[1].searched_text, "Hello")
        self.assertEqual(results[1].line_content, "Hello again.")
        self.assertEqual(results[1].snapshot_name, self.snap.name)

    def test_search_text_not_found(self):
        params = SnapshotSearchParams(
            query="nonexistent",
            search_type=SnapshotSearchType.TEXT
        )
        results = self.searcher.search(self.snap, params)
        self.assertEqual(len(results), 0)

    def test_search_regex_found(self):
        params = SnapshotSearchParams(
            query=r"value=\d+",
            search_type=SnapshotSearchType.REGEX
        )
        results = self.searcher.search(self.snap, params)
        self.assertEqual(len(results), 1)
        self.assertEqual("fileC.log", results[0].file_path.name)
        self.assertEqual(results[0].line_number, 1)
        self.assertEqual(results[0].searched_text, r"value=\d+")
        self.assertEqual(results[0].line_content, "Log file with some data: value=12345")
        self.assertEqual(results[0].snapshot_name, self.snap.name)

    def test_search_regex_invalid_pattern(self):
        params = SnapshotSearchParams(
            query=r"[invalid",
            search_type=SnapshotSearchType.REGEX
        )
        results = self.searcher.search(self.snap, params)
        self.assertEqual(len(results), 0)

    def test_search_with_extension_filter(self):
        params = SnapshotSearchParams(
            query="file",
            search_type=SnapshotSearchType.TEXT,
            extensions=[".txt"]
        )
        results = self.searcher.search(self.snap, params)
        self.assertEqual(len(results), 2)
        for result in results:
            self.assertEqual(result.file_path.suffix, ".txt")

    def test_search_with_extension_filter_no_match(self):
        params = SnapshotSearchParams(
            query="value",
            search_type=SnapshotSearchType.TEXT,
            extensions=[".txt"]
        )
        results = self.searcher.search(self.snap, params)
        self.assertEqual(len(results), 0)

    def test_search_list_multiple_snapshots(self):
        dir3 = SOURCE_DATA_PATH / "search_dir3"
        dir3.mkdir()
        (dir3 / "fileE.txt").write_text("A new file for the second snapshot.\nHello from snap 2.")
        snap2 = Snapshot(
            id="search-snap-id-2",
            name="SearchTestSnap2",
            desc="Second snapshot",
            directories=[
                SnapDirAssociation(index=1, original_path=str(dir3), folder_id="d3"),
            ],
            author="SearchTest"
        )
        self.catalogue.add(snap2)

        params = SnapshotSearchParams(
            query="Hello",
            search_type=SnapshotSearchType.TEXT
        )
        results = self.searcher.search_list([self.snap, snap2], params)
        self.assertEqual(len(results), 3)

        # Check if results are from both snapshots
        snap1_results = [r for r in results if r.snapshot_name == self.snap.name]
        snap2_results = [r for r in results if r.snapshot_name == snap2.name]
        self.assertEqual(len(snap1_results), 2)
        self.assertEqual(len(snap2_results), 1)
        self.assertEqual(snap2_results[0].line_content, "Hello from snap 2.")

    def test_search_list_single_snapshot(self):
        params = SnapshotSearchParams(
            query="Hello",
            search_type=SnapshotSearchType.TEXT
        )
        results = self.searcher.search_list([self.snap], params)
        self.assertEqual(len(results), 2)

    def test_search_with_progress_callback(self):
        progress_reports = []

        def progress_handler(current_file, total_files, current_index):
            progress_reports.append((current_file, total_files, current_index))

        params = SnapshotSearchParams(
            query="file",
            search_type=SnapshotSearchType.TEXT
        )

        self.searcher.search(self.snap, params, on_progress=progress_handler)

        self.assertEqual(len(progress_reports), 5)

        total_files_reported = progress_reports[0][1]
        self.assertEqual(total_files_reported, 5)

        # Check that the current_index increments correctly
        for i, report in enumerate(progress_reports):
            self.assertEqual(report[2], i + 1)

        # Check that file names are reported
        reported_files = {report[0] for report in progress_reports}
        expected_files = {"fileA.txt", "fileB.txt", "fileC.log", "fileD.txt", "binary.bin"}
        self.assertEqual(reported_files, expected_files)

    def test_search_with_progress_and_extensions(self):
        progress_reports = []

        def progress_handler(current_file, total_files, current_index):
            progress_reports.append((current_file, total_files, current_index))

        params = SnapshotSearchParams(
            query="file",
            search_type=SnapshotSearchType.TEXT,
            extensions=[".txt"]
        )

        self.searcher.search(self.snap, params, on_progress=progress_handler)

        self.assertEqual(len(progress_reports), 3)
        self.assertEqual(progress_reports[0][1], 3)  # total_files


if __name__ == '__main__':
    unittest.main(argv=['first-arg-is-ignored'], exit=False)
