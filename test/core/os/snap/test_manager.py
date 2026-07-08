"""
Unit tests for pylizlib.core.os.snap.manager

Covers every public method of SnapshotManager:
    - create            (directory/JSON creation, idempotency via clear)
    - delete            (removes directory, noop when missing)
    - update_json_base_fields
    - update_json_data_fields
    - install_directory / uninstall_directory_by_folder_id
    - update_from_actions_list
    - duplicate         (BUG-2 regression: original must not be mutated)
    - update_associated_dirs_from_system  (success + missing source)
    - install           (content copy, date_last_used update)
    - remove_installed_copies
    - create_backup     (snapshot directory, associated directories, export naming)
"""

import shutil
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from pylizlib.core.log.pylizLogger import logger
from pylizlib.core.data.gen import gen_random_string
from pylizlib.core.os.snap.domain import (
    BackupType,
    SnapDirAssociation,
    Snapshot,
    SnapshotSettings,
)
from pylizlib.core.os.snap.manager import SnapshotManager
from pylizlib.core.os.snap.serializer import SnapshotSerializer
from pylizlib.core.os.snap.utils import SnapshotUtils
from test.core.os.snap.conftest import (
    BACKUP_PATH,
    CATALOGUE_PATH,
    SOURCE_DATA_PATH,
    TEST_LOCAL_ROOT,
    create_source_dirs,
    make_snapshot,
    reset_index,
    setup_test_dirs,
    teardown_test_dirs,
)


class TestSnapshotManagerCreate(unittest.TestCase):
    def setUp(self):
        setup_test_dirs()
        self._src = create_source_dirs(SOURCE_DATA_PATH, ["m1", "m2", "m3"])

    def tearDown(self):
        teardown_test_dirs()

    def _mgr(self, snap, settings=None):
        return SnapshotManager(snap, CATALOGUE_PATH, settings or SnapshotSettings())

    def test_create_builds_directory_and_json(self):
        snap = make_snapshot("MgrCreate", self._src, n=2)
        mgr = self._mgr(snap)
        self.assertFalse(mgr.path_snapshot.exists())
        mgr.create()
        self.assertTrue(mgr.path_snapshot.exists())
        self.assertTrue(mgr.path_snapshot_json.exists())
        for assoc in snap.directories:
            self.assertTrue((mgr.path_snapshot / assoc.directory_name).exists())

    def test_create_clears_existing_contents(self):
        snap = make_snapshot("MgrRecreate", self._src, n=1)
        mgr = self._mgr(snap)
        mgr.create()
        leftover = mgr.path_snapshot / "leftover.txt"
        leftover.write_text("stale")
        mgr.create()
        self.assertFalse(leftover.exists())


class TestSnapshotManagerDelete(unittest.TestCase):
    def setUp(self):
        setup_test_dirs()
        self._src = create_source_dirs(SOURCE_DATA_PATH, ["d1"])

    def tearDown(self):
        teardown_test_dirs()

    def _mgr(self, snap):
        return SnapshotManager(snap, CATALOGUE_PATH, SnapshotSettings())

    def test_delete_removes_directory(self):
        snap = make_snapshot("MgrDel", self._src, n=1)
        mgr = self._mgr(snap)
        mgr.create()
        mgr.delete()
        self.assertFalse(mgr.path_snapshot.exists())

    def test_delete_when_nonexistent_does_not_raise(self):
        snap = make_snapshot("MgrDelNone", self._src, n=1)
        mgr = self._mgr(snap)
        mgr.delete()  # must not raise


class TestSnapshotManagerJsonUpdates(unittest.TestCase):
    def setUp(self):
        setup_test_dirs()
        self._src = create_source_dirs(SOURCE_DATA_PATH, ["j1"])

    def tearDown(self):
        teardown_test_dirs()

    def _mgr(self, snap):
        return SnapshotManager(snap, CATALOGUE_PATH, SnapshotSettings())

    def test_update_json_base_fields(self):
        snap = make_snapshot("BaseFields", self._src, n=1)
        mgr = self._mgr(snap)
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
        snap = make_snapshot("DataFields", self._src, n=1)
        mgr = self._mgr(snap)
        mgr.create()
        snap.data["env"] = "prod"
        mgr.update_json_data_fields()
        loaded = SnapshotSerializer.from_json(mgr.path_snapshot_json)
        self.assertEqual(loaded.data.get("env"), "prod")
        self.assertIsNotNone(loaded.date_last_modified)


class TestSnapshotManagerDirectoryManagement(unittest.TestCase):
    def setUp(self):
        setup_test_dirs()
        self._src = create_source_dirs(SOURCE_DATA_PATH, ["dm1", "dm2"])

    def tearDown(self):
        teardown_test_dirs()

    def _mgr(self, snap):
        return SnapshotManager(snap, CATALOGUE_PATH, SnapshotSettings())

    def test_install_directory_and_then_uninstall_by_folder_id(self):
        snap = make_snapshot("InstDir", self._src, n=1)
        mgr = self._mgr(snap)
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
        snap = make_snapshot("InstDirBad", self._src, n=1)
        mgr = self._mgr(snap)
        mgr.create()
        with self.assertRaises(ValueError):
            mgr.install_directory(SOURCE_DATA_PATH / "does_not_exist")

    def test_uninstall_nonexistent_folder_id_is_noop(self):
        snap = make_snapshot("UninstNoOp", self._src, n=1)
        mgr = self._mgr(snap)
        mgr.create()
        initial_count = len(snap.directories)
        mgr.uninstall_directory_by_folder_id("nonexistent_id")
        self.assertEqual(len(snap.directories), initial_count)


class TestSnapshotManagerDuplicate(unittest.TestCase):
    def setUp(self):
        setup_test_dirs()
        self._src = create_source_dirs(SOURCE_DATA_PATH, ["dup1"])

    def tearDown(self):
        teardown_test_dirs()

    def _mgr(self, snap):
        return SnapshotManager(snap, CATALOGUE_PATH, SnapshotSettings())

    def test_bug2_duplicate_does_not_mutate_original_snapshot(self):
        """BUG-2: duplicate() must NOT change self.snapshot.id or .name."""
        snap = make_snapshot("DupOriginal", self._src, n=1)
        mgr = self._mgr(snap)
        mgr.create()
        original_id = snap.id
        original_name = snap.name
        mgr.duplicate()
        self.assertEqual(snap.id, original_id, "BUG-2: duplicate() mutated original snapshot ID")
        self.assertEqual(snap.name, original_name, "BUG-2: duplicate() mutated original snapshot name")

    def test_duplicate_creates_new_directory_on_disk(self):
        snap = make_snapshot("DupSource", self._src, n=1)
        mgr = self._mgr(snap)
        mgr.create()
        mgr.duplicate()
        all_dirs = [d for d in CATALOGUE_PATH.iterdir() if d.is_dir()]
        self.assertEqual(len(all_dirs), 2)
        new_dir = next(d for d in all_dirs if d.name != snap.id)
        loaded = SnapshotSerializer.from_json(new_dir / SnapshotSettings().json_filename)
        self.assertIn("Copy", loaded.name)
        self.assertNotEqual(loaded.id, snap.id)

    def test_duplicate_raises_when_source_path_missing(self):
        snap = make_snapshot("DupMissing", self._src, n=1)
        mgr = self._mgr(snap)
        with self.assertRaises(FileNotFoundError):
            mgr.duplicate()


class TestSnapshotManagerUpdateAssocDirs(unittest.TestCase):
    def setUp(self):
        setup_test_dirs()
        self._src = create_source_dirs(SOURCE_DATA_PATH, ["ua1"])

    def tearDown(self):
        teardown_test_dirs()

    def _mgr(self, snap):
        return SnapshotManager(snap, CATALOGUE_PATH, SnapshotSettings())

    def test_update_syncs_new_file_from_system(self):
        snap = make_snapshot("UpdateAssoc", self._src, n=1)
        mgr = self._mgr(snap)
        mgr.create()
        original_dir = Path(snap.directories[0].original_path)
        (original_dir / "new_file.txt").write_text("added after create")
        mgr.update_associated_dirs_from_system()
        internal_copy = mgr.path_snapshot / snap.directories[0].directory_name
        self.assertTrue((internal_copy / "new_file.txt").exists())
        loaded = SnapshotSerializer.from_json(mgr.path_snapshot_json)
        self.assertIsNotNone(loaded.date_last_modified)

    def test_missing_source_sets_size_to_zero(self):
        snap = make_snapshot("AssocMissing", self._src, n=1)
        mgr = self._mgr(snap)
        mgr.create()
        original_dir = Path(snap.directories[0].original_path)
        shutil.rmtree(original_dir)
        with self.assertLogs(level="WARNING"):
            mgr.update_associated_dirs_from_system()
        loaded = SnapshotSerializer.from_json(mgr.path_snapshot_json)
        self.assertEqual(loaded.directories[0].mb_size, 0.0)


class TestSnapshotManagerInstall(unittest.TestCase):
    def setUp(self):
        setup_test_dirs()
        self._src = create_source_dirs(SOURCE_DATA_PATH, ["i1"])

    def tearDown(self):
        teardown_test_dirs()

    def _mgr(self, snap):
        return SnapshotManager(snap, CATALOGUE_PATH, SnapshotSettings())

    def test_install_copies_content_to_original_path(self):
        snap = make_snapshot("MgrInstall", self._src, n=1)
        mgr = self._mgr(snap)
        mgr.create()
        original_dir = Path(snap.directories[0].original_path)
        (original_dir / "extra.txt").write_text("should be removed")
        mgr.install()
        self.assertFalse((original_dir / "extra.txt").exists())
        self.assertTrue((original_dir / "i1_file.txt").exists())

    def test_install_updates_date_last_used_in_json(self):
        snap = make_snapshot("MgrInstallDate", self._src, n=1)
        mgr = self._mgr(snap)
        mgr.create()
        mgr.install()
        loaded = SnapshotSerializer.from_json(mgr.path_snapshot_json)
        self.assertIsNotNone(loaded.date_last_used)

    def test_remove_installed_copies_deletes_original_paths(self):
        install_dir = TEST_LOCAL_ROOT / "installed_copy"
        install_dir.mkdir(parents=True)
        (install_dir / "a.txt").write_text("x")
        reset_index()
        snap = Snapshot(
            id=gen_random_string(8),
            name="RemoveSnap",
            desc="",
            directories=[SnapDirAssociation(index=1, original_path=str(install_dir), folder_id="rem1")],
        )
        mgr = SnapshotManager(snap, CATALOGUE_PATH, SnapshotSettings())
        self.assertTrue(install_dir.exists())
        mgr.remove_installed_copies()
        self.assertFalse(install_dir.exists())


class TestSnapshotManagerActionsAndBackup(unittest.TestCase):
    def setUp(self):
        setup_test_dirs()
        self._src = create_source_dirs(SOURCE_DATA_PATH, ["ab1", "ab2", "ab3"])

    def tearDown(self):
        teardown_test_dirs()

    def _mgr(self, snap, settings=None):
        return SnapshotManager(snap, CATALOGUE_PATH, settings or SnapshotSettings())

    def test_update_from_actions_list_applies_add_and_remove(self):
        src_sorted = sorted(self._src)
        snap = make_snapshot("ActionsSnap", src_sorted, n=2)
        mgr = self._mgr(snap)
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

    def test_create_backup_snapshot_directory(self):
        snap = make_snapshot("BckSnap", self._src, n=1)
        mgr = self._mgr(snap)
        mgr.create()
        mgr.create_backup(BACKUP_PATH, "test_prefix", BackupType.SNAPSHOT_DIRECTORY)
        zips = list(BACKUP_PATH.glob("*.zip"))
        self.assertEqual(len(zips), 1)
        self.assertIn("test_prefix", zips[0].name)

    def test_create_backup_associated_directories_contains_source_files(self):
        snap = make_snapshot("BckAssoc", self._src, n=1)
        mgr = self._mgr(snap)
        mgr.create()
        mgr.create_backup(BACKUP_PATH, "assoc_bck", BackupType.ASSOCIATED_DIRECTORIES)
        zips = list(BACKUP_PATH.glob("*.zip"))
        self.assertEqual(len(zips), 1)
        with zipfile.ZipFile(zips[0]) as zf:
            names = zf.namelist()
        self.assertTrue(any("ab1_file.txt" in n for n in names))

    def test_create_backup_export_naming(self):
        snap = make_snapshot("ExpSnap", self._src, n=1)
        mgr = self._mgr(snap)
        mgr.create()
        mgr.create_backup(BACKUP_PATH, "export", BackupType.SNAPSHOT_DIRECTORY, is_export=True)
        zips = list(BACKUP_PATH.glob("*.zip"))
        self.assertEqual(len(zips), 1)
        self.assertTrue(zips[0].name.startswith("export_"))

    def test_create_backup_non_export_naming_has_backup_prefix(self):
        snap = make_snapshot("NonExpSnap", self._src, n=1)
        mgr = self._mgr(snap)
        mgr.create()
        mgr.create_backup(BACKUP_PATH, "prefix2", BackupType.SNAPSHOT_DIRECTORY, is_export=False)
        zips = list(BACKUP_PATH.glob("*.zip"))
        self.assertEqual(len(zips), 1)
        self.assertTrue(zips[0].name.startswith("backup_prefix2"))


class TestSnapshotManagerCoverage(unittest.TestCase):
    def setUp(self):
        setup_test_dirs()
        self._src = create_source_dirs(SOURCE_DATA_PATH, ["cov1"])

    def tearDown(self):
        teardown_test_dirs()

    def test_remove_installed_copies_exceptions(self):
        # coverage 229-232
        snap = make_snapshot("RemCov", self._src, n=1)
        mgr = SnapshotManager(snap, CATALOGUE_PATH, SnapshotSettings())
        mgr.create()
        install_path = Path(snap.directories[0].original_path)
        
        # Test 231-232
        shutil.rmtree(install_path)
        with self.assertLogs(level="DEBUG") as cm:
            logger.setLevel("DEBUG")
            mgr.remove_installed_copies()
        self.assertTrue(any("does not exist or is not a directory" in out for out in cm.output))
        
        # Test 229-230
        install_path.mkdir(parents=True, exist_ok=True)
        with patch('shutil.rmtree', side_effect=Exception("mocked error")):
            with self.assertLogs(level="ERROR") as cm2:
                mgr.remove_installed_copies()
            self.assertTrue(any("Failed to remove directory" in out for out in cm2.output))

    @patch('sys.platform', 'win32')
    def test_install_win32_no_pywin32(self):
        # coverage 247-252
        snap = make_snapshot("Win32NoPywin32", self._src, n=1)
        mgr = SnapshotManager(snap, CATALOGUE_PATH, SnapshotSettings())
        mgr.create()
        with patch.dict('sys.modules', {'ntsecuritycon': None, 'win32security': None}):
            with self.assertLogs(level="ERROR") as cm:
                mgr.install()
            self.assertTrue(any("pywin32 not installed" in out for out in cm.output))

    @patch('sys.platform', 'win32')
    def test_install_win32_with_pywin32_success(self):
        # coverage 295-306
        snap = make_snapshot("Win32Pywin32Succ", self._src, n=1)
        mgr = SnapshotManager(snap, CATALOGUE_PATH, SnapshotSettings())
        mgr.create()
        import types
        mock_win32security = types.ModuleType('win32security')
        mock_ntsecuritycon = types.ModuleType('ntsecuritycon')
        
        mock_win32security.LookupAccountName = MagicMock(return_value=("everyone_sid", "domain", 1))
        mock_win32security.DACL_SECURITY_INFORMATION = 1
        mock_win32security.ACL_REVISION = 2
        mock_win32security.SetFileSecurity = MagicMock()
        
        mock_sd = MagicMock()
        mock_dacl = MagicMock()
        mock_sd.GetSecurityDescriptorDacl.return_value = mock_dacl
        mock_win32security.GetFileSecurity = MagicMock(return_value=mock_sd)
        
        mock_ntsecuritycon.OBJECT_INHERIT_ACE = 1
        mock_ntsecuritycon.CONTAINER_INHERIT_ACE = 2
        mock_ntsecuritycon.GENERIC_ALL = 3
        
        with patch.dict('sys.modules', {'ntsecuritycon': mock_ntsecuritycon, 'win32security': mock_win32security}):
            mgr.install()
            mock_win32security.LookupAccountName.assert_called()
            mock_win32security.GetFileSecurity.assert_called()
            mock_dacl.AddAccessAllowedAceEx.assert_called()
            mock_sd.SetSecurityDescriptorDacl.assert_called()
            mock_win32security.SetFileSecurity.assert_called()

    @patch('sys.platform', 'win32')
    def test_install_win32_with_pywin32_exceptions(self):
        # coverage 290-313
        snap = make_snapshot("Win32Pywin32", self._src, n=1)
        mgr = SnapshotManager(snap, CATALOGUE_PATH, SnapshotSettings())
        mgr.create()
        import types
        mock_win32security = types.ModuleType('win32security')
        mock_ntsecuritycon = types.ModuleType('ntsecuritycon')
        
        mock_win32security.LookupAccountName = MagicMock(side_effect=Exception("win32 error"))
        
        with patch.dict('sys.modules', {'ntsecuritycon': mock_ntsecuritycon, 'win32security': mock_win32security}):
            with self.assertLogs(level="ERROR") as cm:
                mgr.install()
            self.assertTrue(any("Failed to set permissions" in out for out in cm.output))

    def test_install_remove_and_copy_exceptions(self):
        # coverage 270, 273-274, 282, 285-286
        snap = make_snapshot("InstallExceptions", self._src, n=1)
        mgr = SnapshotManager(snap, CATALOGUE_PATH, SnapshotSettings())
        mgr.create()
        
        install_location = Path(snap.directories[0].original_path)
        install_location.mkdir(parents=True, exist_ok=True)
        (install_location / "some_dir").mkdir()
        (install_location / "some_file.txt").write_text("x")
        
        source_dir = mgr.path_snapshot / snap.directories[0].directory_name
        (source_dir / "src_dir").mkdir()
        (source_dir / "src_file.txt").write_text("x")
        
        with patch('shutil.rmtree', side_effect=Exception("rmtree err")), \
             patch('pathlib.Path.unlink', side_effect=Exception("unlink err")), \
             patch('shutil.copytree', side_effect=Exception("copytree err")), \
             patch('shutil.copy2', side_effect=Exception("copy2 err")):
            with self.assertLogs(level="ERROR") as cm:
                mgr.install()
            out = " ".join(cm.output)
            self.assertIn("Could not remove item", out)
            self.assertIn("Could not copy item", out)

    def test_create_backup_exceptions(self):
        # coverage 371-372
        snap = make_snapshot("BackupExceptions", self._src, n=1)
        mgr = SnapshotManager(snap, CATALOGUE_PATH, SnapshotSettings())
        mgr.create()
        with patch('zipfile.ZipFile', side_effect=Exception("zip error")):
            with self.assertLogs(level="ERROR") as cm:
                mgr.create_backup(BACKUP_PATH, "pref", BackupType.SNAPSHOT_DIRECTORY)
            self.assertIn("zip error", " ".join(cm.output))


if __name__ == "__main__":
    unittest.main()
