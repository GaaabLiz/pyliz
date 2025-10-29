import unittest
from pathlib import Path
import shutil
from datetime import datetime

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
        (SOURCE_DATA_PATH / "dir3").mkdir()
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
        self.assertTrue(any(f.name.startswith(f"backup_snapdir_{snap1.id}") for f in BACKUP_PATH.iterdir()))

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
        self.assertTrue(any(f.name.startswith(f"backup_snapdir_{snap_new.id}") for f in BACKUP_PATH.iterdir()))

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
        self.assertTrue(any(f.name.startswith(f"backup_preinstall_{snap1.id}") for f in BACKUP_PATH.iterdir()))

        # Check last used date
        updated_snap = self.catalogue.get_by_id(snap1.id)
        self.assertIsNotNone(updated_snap.date_last_used)


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
        results = self.searcher.search_text("Hello")
        self.assertEqual(len(results), 2)

        # Sort results to have a predictable order for assertions
        results.sort(key=lambda r: r.file_path)

        self.assertIn("fileA.txt", results[0].file_path)
        self.assertEqual(results[0].line_number, 1)
        self.assertEqual(results[0].searched_text, "Hello")

        self.assertIn("fileB.txt", results[1].file_path)
        self.assertEqual(results[1].line_number, 2)
        self.assertEqual(results[1].searched_text, "Hello")

    def test_search_text_not_found(self):
        results = self.searcher.search_text("nonexistent")
        self.assertEqual(len(results), 0)

    def test_search_text_single_match(self):
        results = self.searcher.search_text("value=12345")
        self.assertEqual(len(results), 1)
        self.assertIn("fileC.log", results[0].file_path)
        self.assertEqual(results[0].line_number, 1)

    def test_search_regex_found(self):
        results = self.searcher.search_regex(r"value=\d+")
        self.assertEqual(len(results), 1)
        self.assertIn("fileC.log", results[0].file_path)
        self.assertEqual(results[0].line_number, 1)
        self.assertEqual(results[0].searched_text, r"value=\d+")

    def test_search_regex_multiple_matches(self):
        results = self.searcher.search_regex(r"\bfile\b")  # match whole word 'file'
        self.assertEqual(len(results), 3)

    def test_search_regex_not_found(self):
        results = self.searcher.search_regex(r"nonexistent\d{5}")
        self.assertEqual(len(results), 0)

    def test_search_regex_invalid_pattern(self):
        # An invalid regex should be handled gracefully (log an error and return empty list)
        results = self.searcher.search_regex(r"[invalid")
        self.assertEqual(len(results), 0)


if __name__ == '__main__':
    unittest.main(argv=['first-arg-is-ignored'], exit=False)
