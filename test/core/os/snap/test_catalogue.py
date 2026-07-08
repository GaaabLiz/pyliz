"""
Unit tests for pylizlib.core.os.snap.catalogue

Covers every public method of SnapshotCatalogue:
    - __init__ (creates directory)
    - set_catalogue_path
    - add / get_all / get_by_id / exists / get_snap_directory_path
    - delete (with and without backup)
    - install (content copy, date_last_used, backup trigger)
    - update_snapshot_by_objs / update_snapshot_by_edits (with backup trigger)
    - duplicate_by_id (and error branch)
    - export_snapshot / import_snapshot (happy path + all error branches)
    - export_catalogue / import_catalogue (happy path + skip-existing + invalid-zip)
    - export_assoc_dirs (happy path + error branch)
    - update_assoc_with_installed / remove_installed_copies
    - list_backups / restore_backup (_sd, _ad, and error branches)
"""

import shutil
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from pylizlib.core.data.gen import gen_random_string
from pylizlib.core.os.snap.domain import (
    BackupType,
    SnapDirAssociation,
    Snapshot,
    SnapshotSettings,
)
from pylizlib.core.os.snap.manager import SnapshotManager
from pylizlib.core.os.snap.catalogue import SnapshotCatalogue
from pylizlib.core.os.snap.serializer import SnapshotSerializer
from test.core.os.snap.conftest import (
    BACKUP_PATH,
    CATALOGUE_PATH,
    INSTALL_DEST_PATH,
    SOURCE_DATA_PATH,
    TEST_LOCAL_ROOT,
    create_source_dirs,
    make_snapshot,
    reset_index,
    setup_test_dirs,
    teardown_test_dirs,
)


def _cat(settings=None) -> SnapshotCatalogue:
    return SnapshotCatalogue(CATALOGUE_PATH, settings=settings or SnapshotSettings())


def _cat_with_backup() -> SnapshotCatalogue:
    settings = SnapshotSettings(
        backup_path=BACKUP_PATH,
        backup_pre_install=True,
        backup_pre_modify=True,
        backup_pre_delete=True,
    )
    return SnapshotCatalogue(CATALOGUE_PATH, settings=settings)


class TestSnapshotCatalogueInit(unittest.TestCase):
    def setUp(self):
        setup_test_dirs()

    def tearDown(self):
        teardown_test_dirs()

    def test_init_creates_directory(self):
        new_path = TEST_LOCAL_ROOT / "new_cat"
        SnapshotCatalogue(new_path)
        self.assertTrue(new_path.exists())

    def test_set_catalogue_path_creates_new_directory(self):
        cat = _cat()
        new_path = TEST_LOCAL_ROOT / "moved_cat"
        cat.set_catalogue_path(new_path)
        self.assertTrue(new_path.exists())
        self.assertEqual(cat.path_catalogue, new_path)


class TestSnapshotCatalogueCRUD(unittest.TestCase):
    def setUp(self):
        setup_test_dirs()
        self._src = create_source_dirs(SOURCE_DATA_PATH, ["c1", "c2", "c3"])
        self.cat = _cat()

    def tearDown(self):
        teardown_test_dirs()

    def test_add_get_all_get_by_id_exists_cycle(self):
        self.assertEqual(len(self.cat.get_all()), 0)
        snap = make_snapshot("CatSnap1", self._src, n=1)
        self.cat.add(snap)
        self.assertEqual(len(self.cat.get_all()), 1)
        self.assertTrue(self.cat.exists(snap.id))
        self.assertFalse(self.cat.exists("nonexistent"))
        retrieved = self.cat.get_by_id(snap.id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.id, snap.id)
        self.assertIsNone(self.cat.get_by_id("nonexistent"))

    def test_add_multiple_snapshots(self):
        for i in range(3):
            self.cat.add(make_snapshot(f"Multi{i}", self._src, n=1))
        self.assertEqual(len(self.cat.get_all()), 3)

    def test_delete_removes_snapshot(self):
        snap = make_snapshot("DelSnap", self._src, n=1)
        self.cat.add(snap)
        self.cat.delete(snap)
        self.assertFalse(self.cat.exists(snap.id))

    def test_get_snap_directory_path_returns_existing_path(self):
        snap = make_snapshot("DirPath", self._src, n=1)
        self.cat.add(snap)
        path = self.cat.get_snap_directory_path(snap)
        self.assertIsNotNone(path)
        self.assertTrue(path.exists())

    def test_get_snap_directory_path_returns_none_for_nonexistent(self):
        snap = Snapshot(id="ghost_id", name="X", desc="")
        self.assertIsNone(self.cat.get_snap_directory_path(snap))


class TestSnapshotCatalogueBackupTriggers(unittest.TestCase):
    def setUp(self):
        setup_test_dirs()
        self._src = create_source_dirs(SOURCE_DATA_PATH, ["bt1"])
        self.cat = _cat_with_backup()

    def tearDown(self):
        teardown_test_dirs()

    def test_delete_creates_backup_when_enabled(self):
        snap = make_snapshot("DelBck", self._src, n=1)
        self.cat.add(snap)
        self.cat.delete(snap)
        backups = list(BACKUP_PATH.glob("backup_beforeDelete_*.zip"))
        self.assertEqual(len(backups), 1)

    def test_install_creates_backup_when_enabled(self):
        snap = make_snapshot("InstBck", self._src, n=1)
        self.cat.add(snap)
        self.cat.install(snap)
        self.assertEqual(len(list(BACKUP_PATH.glob("backup_preinstall_*.zip"))), 1)

    def test_update_creates_backup_when_enabled(self):
        snap = make_snapshot("UpdBck", self._src, n=1)
        self.cat.add(snap)
        clone = snap.clone()
        clone.name = "UpdBckChanged"
        self.cat.update_snapshot_by_objs(snap, clone)
        self.assertEqual(len(list(BACKUP_PATH.glob("backup_beforeEdit_*.zip"))), 1)


class TestSnapshotCatalogueInstall(unittest.TestCase):
    def setUp(self):
        setup_test_dirs()
        self._src = create_source_dirs(SOURCE_DATA_PATH, ["ins1"])
        self.cat = _cat()

    def tearDown(self):
        teardown_test_dirs()

    def test_install_replaces_destination_contents(self):
        snap = make_snapshot("InstallSnap", self._src, n=1)
        self.cat.add(snap)
        target = Path(snap.directories[0].original_path)
        (target / "stale.txt").write_text("stale")
        self.cat.install(snap)
        self.assertFalse((target / "stale.txt").exists())
        self.assertTrue((target / "ins1_file.txt").exists())

    def test_install_records_date_last_used(self):
        snap = make_snapshot("InstallDate", self._src, n=1)
        self.cat.add(snap)
        self.cat.install(snap)
        updated = self.cat.get_by_id(snap.id)
        self.assertIsNotNone(updated.date_last_used)


class TestSnapshotCatalogueUpdate(unittest.TestCase):
    def setUp(self):
        setup_test_dirs()
        self._src = create_source_dirs(SOURCE_DATA_PATH, ["u1", "u2", "u3"])
        self.cat = _cat()

    def tearDown(self):
        teardown_test_dirs()

    def test_update_by_objs_applies_name_and_directory_changes(self):
        src_sorted = sorted(self._src)
        old = make_snapshot("UpdateOld", src_sorted, n=2)
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


class TestSnapshotCatalogueDuplicate(unittest.TestCase):
    def setUp(self):
        setup_test_dirs()
        self._src = create_source_dirs(SOURCE_DATA_PATH, ["dp1"])
        self.cat = _cat()

    def tearDown(self):
        teardown_test_dirs()

    def test_duplicate_by_id_creates_copy_with_different_id(self):
        snap = make_snapshot("DupById", self._src, n=1)
        self.cat.add(snap)
        self.cat.duplicate_by_id(snap.id)
        all_snaps = self.cat.get_all()
        self.assertEqual(len(all_snaps), 2)
        copy_snap = next(s for s in all_snaps if s.id != snap.id)
        self.assertIn("Copy", copy_snap.name)

    def test_duplicate_by_id_raises_on_nonexistent(self):
        with self.assertRaises(ValueError):
            self.cat.duplicate_by_id("nonexistent_id")


class TestSnapshotCatalogueImportExport(unittest.TestCase):
    def setUp(self):
        setup_test_dirs()
        self._src = create_source_dirs(SOURCE_DATA_PATH, ["ie1"])
        self.cat = _cat()
        self._export_dir = TEST_LOCAL_ROOT / "exp"
        self._export_dir.mkdir(parents=True)

    def tearDown(self):
        teardown_test_dirs()

    def test_export_and_import_snapshot_round_trip(self):
        snap = make_snapshot("ExpImpSnap", self._src, n=1)
        self.cat.add(snap)
        self.cat.export_snapshot(snap.id, self._export_dir)
        zips = list(self._export_dir.glob("*.zip"))
        self.assertEqual(len(zips), 1)

        self.cat.delete(snap)
        self.assertFalse(self.cat.exists(snap.id))

        self.cat.import_snapshot(zips[0])
        self.assertTrue(self.cat.exists(snap.id))
        imp = self.cat.get_by_id(snap.id)
        self.assertEqual(imp.name, snap.name)

    def test_import_snapshot_raises_on_duplicate_id(self):
        snap = make_snapshot("DupImpSnap", self._src, n=1)
        self.cat.add(snap)
        self.cat.export_snapshot(snap.id, self._export_dir)
        zip_path = list(self._export_dir.glob("*.zip"))[0]
        with self.assertRaises(ValueError) as ctx:
            self.cat.import_snapshot(zip_path)
        self.assertIn("already exists", str(ctx.exception))

    def test_import_snapshot_raises_on_invalid_zip_content(self):
        bad = TEST_LOCAL_ROOT / "bad.zip"
        bad.write_text("not a zip")
        with self.assertRaises(ValueError):
            self.cat.import_snapshot(bad)

    def test_import_snapshot_raises_on_non_zip_extension(self):
        notzip = TEST_LOCAL_ROOT / "file.txt"
        notzip.write_text("x")
        with self.assertRaises(ValueError):
            self.cat.import_snapshot(notzip)

    def test_import_snapshot_raises_when_json_missing_from_zip(self):
        empty_zip = TEST_LOCAL_ROOT / "empty.zip"
        with zipfile.ZipFile(empty_zip, "w") as zf:
            zf.writestr("dummy.txt", "hello")
        with self.assertRaises(ValueError) as ctx:
            self.cat.import_snapshot(empty_zip)
        self.assertIn("snapshot json file", str(ctx.exception))

    def test_export_and_import_full_catalogue(self):
        for i in range(3):
            self.cat.add(make_snapshot(f"CatExp{i}", self._src, n=1))
        self.cat.export_catalogue(self._export_dir, "cat.zip")
        self.assertTrue((self._export_dir / "cat.zip").exists())

        for s in self.cat.get_all():
            self.cat.delete(s)
        self.assertEqual(len(self.cat.get_all()), 0)
        self.cat.import_catalogue(self._export_dir / "cat.zip")
        self.assertEqual(len(self.cat.get_all()), 3)

    def test_export_catalogue_empty_logs_warning(self):
        with self.assertLogs(level="WARNING"):
            self.cat.export_catalogue(self._export_dir, "empty.zip")

    def test_import_catalogue_skips_existing_snapshots(self):
        s1 = make_snapshot("Skip1", self._src, n=1)
        s2 = make_snapshot("Skip2", self._src, n=1)
        self.cat.add(s1)
        self.cat.add(s2)
        self.cat.export_catalogue(self._export_dir, "skip.zip")
        self.cat.delete(s2)
        self.assertEqual(len(self.cat.get_all()), 1)

        with patch("pylizlib.core.log.pylizLogger.logger.info") as mock_info:
            self.cat.import_catalogue(self._export_dir / "skip.zip")
            mock_info.assert_any_call(f"Snapshot with ID '{s1.id}' already exists. Skipping import.")
            mock_info.assert_any_call(f"Successfully imported snapshot with ID '{s2.id}'.")
        self.assertEqual(len(self.cat.get_all()), 2)

    def test_import_catalogue_raises_on_invalid_zip(self):
        bad = TEST_LOCAL_ROOT / "bad_cat.zip"
        bad.write_text("not a zip")
        with self.assertRaises(ValueError):
            self.cat.import_catalogue(bad)

    def test_export_assoc_dirs_creates_zip_with_ad_suffix(self):
        snap = make_snapshot("ExpAssoc", self._src, n=1)
        self.cat.add(snap)
        self.cat.export_assoc_dirs(snap.id, self._export_dir)
        zips = list(self._export_dir.glob("*.zip"))
        self.assertEqual(len(zips), 1)
        self.assertIn("_ad_", zips[0].name)

    def test_export_assoc_dirs_raises_on_nonexistent_id(self):
        with self.assertRaises(ValueError):
            self.cat.export_assoc_dirs("nonexistent_id", TEST_LOCAL_ROOT)

    def test_export_snapshot_raises_on_nonexistent_id(self):
        with self.assertRaises(ValueError):
            self.cat.export_snapshot("nonexistent_id", TEST_LOCAL_ROOT)


class TestSnapshotCatalogueAssocUpdate(unittest.TestCase):
    def setUp(self):
        setup_test_dirs()
        self._src = create_source_dirs(SOURCE_DATA_PATH, ["au1"])
        self.cat = _cat()

    def tearDown(self):
        teardown_test_dirs()

    def test_update_assoc_with_installed_syncs_filesystem_changes(self):
        snap = make_snapshot("UpdAssoc", self._src, n=1)
        self.cat.add(snap)
        self.cat.install(snap)
        original_dir = Path(snap.directories[0].original_path)
        (original_dir / "added_after_install.txt").write_text("added")
        self.cat.update_assoc_with_installed(snap.id)
        snap_dir = self.cat.get_snap_directory_path(snap)
        internal = snap_dir / snap.directories[0].directory_name
        self.assertTrue((internal / "added_after_install.txt").exists())

    def test_update_assoc_with_installed_raises_on_nonexistent_id(self):
        with self.assertRaises(ValueError):
            self.cat.update_assoc_with_installed("nonexistent_id")

    def test_remove_installed_copies_deletes_all_original_paths(self):
        install1 = INSTALL_DEST_PATH / "rem1"
        install2 = INSTALL_DEST_PATH / "rem2"
        install1.mkdir(parents=True)
        install2.mkdir(parents=True)
        (install1 / "f.txt").write_text("x")
        (install2 / "f.txt").write_text("x")
        reset_index()
        snap = Snapshot(
            id=gen_random_string(8),
            name="RemInstalled",
            desc="",
            directories=[
                SnapDirAssociation(index=1, original_path=str(install1), folder_id="ri1"),
                SnapDirAssociation(index=2, original_path=str(install2), folder_id="ri2"),
            ],
        )
        self.cat.add(snap)
        self.cat.remove_installed_copies(snap.id)
        self.assertFalse(install1.exists())
        self.assertFalse(install2.exists())

    def test_remove_installed_copies_warns_on_nonexistent_snapshot(self):
        with self.assertLogs(level="WARNING"):
            self.cat.remove_installed_copies("nonexistent_id")


class TestSnapshotCatalogueBackupAndRestore(unittest.TestCase):
    def setUp(self):
        setup_test_dirs()
        self._src = create_source_dirs(SOURCE_DATA_PATH, ["br1"])
        self.settings = SnapshotSettings(backup_path=BACKUP_PATH)
        self.cat = SnapshotCatalogue(CATALOGUE_PATH, settings=self.settings)

    def tearDown(self):
        teardown_test_dirs()

    def test_list_backups_returns_sorted_entries_with_correct_types(self):
        snap = make_snapshot("ListBackups", self._src, n=1)
        self.cat.add(snap)
        mgr = SnapshotManager(snap, CATALOGUE_PATH, self.settings)
        mgr.create_backup(BACKUP_PATH, "beforeEdit", BackupType.SNAPSHOT_DIRECTORY)
        mgr.create_backup(BACKUP_PATH, "preinstall", BackupType.ASSOCIATED_DIRECTORIES)
        backups = self.cat.list_backups(BACKUP_PATH)
        self.assertGreaterEqual(len(backups), 2)
        types = {b.backup_type for b in backups}
        self.assertIn(BackupType.SNAPSHOT_DIRECTORY, types)
        self.assertIn(BackupType.ASSOCIATED_DIRECTORIES, types)
        for bck in backups:
            self.assertTrue(bck.path.exists())
            self.assertTrue(bck.file_name.endswith(".zip"))

    def test_list_backups_raises_on_invalid_folder(self):
        with self.assertRaises(ValueError):
            self.cat.list_backups(TEST_LOCAL_ROOT / "does_not_exist")

    def test_restore_backup_snapshot_directory(self):
        snap = make_snapshot("RestoreSD", self._src, n=1)
        self.cat.add(snap)
        mgr = SnapshotManager(snap, CATALOGUE_PATH, self.settings)
        mgr.create_backup(BACKUP_PATH, "beforeDelete", BackupType.SNAPSHOT_DIRECTORY)
        backup_zip = sorted(BACKUP_PATH.glob("*_*_sd_*.zip"))[-1]

        shutil.rmtree(CATALOGUE_PATH / snap.id)
        self.assertFalse((CATALOGUE_PATH / snap.id).exists())

        self.cat.restore_backup(backup_zip)
        self.assertTrue((CATALOGUE_PATH / snap.id).exists())
        restored = self.cat.get_by_id(snap.id)
        self.assertIsNotNone(restored)
        self.assertEqual(restored.id, snap.id)

    def test_restore_backup_associated_directories(self):
        snap = make_snapshot("RestoreAD", self._src, n=1)
        self.cat.add(snap)
        source_dir = Path(snap.directories[0].original_path)
        target_file = source_dir / "br1_file.txt"
        original_content = target_file.read_text()

        mgr = SnapshotManager(snap, CATALOGUE_PATH, self.settings)
        mgr.create_backup(BACKUP_PATH, "preinstall", BackupType.ASSOCIATED_DIRECTORIES)
        backup_zip = sorted(BACKUP_PATH.glob("*_*_ad_*.zip"))[-1]

        target_file.write_text("CORRUPTED")
        self.cat.restore_backup(backup_zip)
        self.assertEqual(target_file.read_text(), original_content)

    def test_restore_backup_raises_on_unknown_type(self):
        unknown_zip = BACKUP_PATH / "unknown_backup.zip"
        with zipfile.ZipFile(unknown_zip, "w") as zf:
            zf.writestr("dummy.txt", "x")
        with self.assertRaises(ValueError):
            self.cat.restore_backup(unknown_zip)

    def test_restore_backup_ad_raises_when_snapshot_missing(self):
        snap = make_snapshot("RestoreADMissing", self._src, n=1)
        self.cat.add(snap)
        mgr = SnapshotManager(snap, CATALOGUE_PATH, self.settings)
        mgr.create_backup(BACKUP_PATH, "preinstall", BackupType.ASSOCIATED_DIRECTORIES)
        backup_zip = sorted(BACKUP_PATH.glob("*_*_ad_*.zip"))[-1]
        shutil.rmtree(CATALOGUE_PATH / snap.id)
        with self.assertRaises(ValueError):
            self.cat.restore_backup(backup_zip)


class TestSnapshotCatalogueCoverage(unittest.TestCase):
    def setUp(self):
        setup_test_dirs()
        self._src = create_source_dirs(SOURCE_DATA_PATH, ["cov1"])
        self.settings = SnapshotSettings(backup_path=BACKUP_PATH)
        self.cat = SnapshotCatalogue(CATALOGUE_PATH, settings=self.settings)

    def tearDown(self):
        teardown_test_dirs()

    def test_parse_backup_info_invalid_date(self):
        # coverage for lines 67-68
        path = BACKUP_PATH / "backup_pref_id_ad_99999999_999999.zip"
        info = self.cat._parse_backup_info(path)
        self.assertIsNone(info.created_at)

    def test_restore_backup_invalid_path(self):
        # coverage for line 135
        with self.assertRaises(ValueError):
            self.cat.restore_backup(BACKUP_PATH / "nonexistent.zip")
            
        with self.assertRaises(ValueError):
            notzip = BACKUP_PATH / "notzip.txt"
            notzip.write_text("")
            self.cat.restore_backup(notzip)

    @patch('zipfile.ZipFile')
    def test_restore_backup_zip_exceptions(self, mock_zip):
        # coverage for 149-152
        mock_zip.side_effect = zipfile.BadZipFile("bad zip")
        zip_path = BACKUP_PATH / "fake_id_sd_20230101_120000.zip"
        zip_path.touch()
        with self.assertRaises(ValueError):
            self.cat.restore_backup(zip_path)
        
        mock_zip.side_effect = Exception("other error")
        with self.assertRaises(IOError):
            self.cat.restore_backup(zip_path)

    def test_restore_backup_sd_no_json(self):
        # coverage for 157
        zip_path = BACKUP_PATH / "backup_pref_id_sd_20230101_120000.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("dummy.txt", "x")
        with self.assertRaises(ValueError):
            self.cat.restore_backup(zip_path)

    def test_restore_backup_sd_destination_exists(self):
        # coverage for 165
        snap = make_snapshot("RestoreSDDest", self._src, n=1)
        self.cat.add(snap)
        mgr = SnapshotManager(snap, CATALOGUE_PATH, self.settings)
        mgr.create_backup(BACKUP_PATH, "bck", BackupType.SNAPSHOT_DIRECTORY)
        backup_zip = sorted(BACKUP_PATH.glob("*_*_sd_*.zip"))[-1]
        
        # Keep directory so destination_path.exists() is true
        self.cat.restore_backup(backup_zip)
        self.assertTrue((CATALOGUE_PATH / snap.id).exists())

    def test_restore_backup_ad_no_snapshot_id(self):
        # coverage for 171
        zip_path = BACKUP_PATH / "backup__ad_20230101_120000.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("dummy.txt", "x")
        with self.assertRaises(ValueError):
            self.cat.restore_backup(zip_path)

    def test_restore_backup_ad_extracted_file_not_dir(self):
        # coverage for 187
        snap = make_snapshot("RestoreADFile", self._src, n=1)
        self.cat.add(snap)
        zip_path = BACKUP_PATH / f"backup_pref_{snap.id}_ad_20230101_120000.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("dummy.txt", "x")
        with self.assertRaises(ValueError):
            self.cat.restore_backup(zip_path)

    def test_restore_backup_ad_unmatched_or_ambiguous_dir(self):
        # coverage for 191-194, 196
        snap = make_snapshot("RestoreADUnmatch", self._src, n=1)
        # Force ambiguous: two directories with same name
        assoc2 = SnapDirAssociation(index=2, original_path=snap.directories[0].original_path + "_other/same", folder_id="other")
        assoc2.original_path = snap.directories[0].original_path
        snap.directories.append(assoc2)
        self.cat.add(snap)
        
        zip_path = BACKUP_PATH / f"backup_pref_{snap.id}_ad_20230101_120000.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("unmatched_dir/file.txt", "x")
            zf.writestr(Path(snap.directories[0].original_path).name + "/file.txt", "x")
            
        with self.assertRaises(ValueError) as ctx:
            self.cat.restore_backup(zip_path)
        self.assertIn("Ambiguous restore target", str(ctx.exception))

    def test_restore_backup_ad_restore_items(self):
        # coverage for 206, 213, 220
        snap = make_snapshot("RestoreADItems", self._src, n=1)
        self.cat.add(snap)
        zip_path = BACKUP_PATH / f"backup_pref_{snap.id}_ad_20230101_120000.zip"
        
        dir_name = Path(snap.directories[0].original_path).name
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr(f"{dir_name}/subdir/file.txt", "x")
            zf.writestr(f"{dir_name}/file.txt", "x")
            
        # Put a subdir and file in destination to trigger removal
        dest = Path(snap.directories[0].original_path)
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "old_subdir").mkdir()
        (dest / "old_file.txt").write_text("x")
        
        self.cat.restore_backup(zip_path)
        self.assertTrue((dest / "subdir" / "file.txt").exists())

    def test_import_catalogue_invalid_path(self):
        # coverage for 414
        with self.assertRaises(ValueError):
            self.cat.import_catalogue(BACKUP_PATH / "nonexistent.zip")

    @patch('zipfile.ZipFile')
    def test_import_catalogue_exceptions(self, mock_zip):
        # coverage for 425-426
        mock_zip.side_effect = zipfile.BadZipFile("bad zip")
        zip_path = BACKUP_PATH / "fake.zip"
        zip_path.touch()
        with self.assertRaises(ValueError):
            self.cat.import_catalogue(zip_path)
        
        mock_zip.side_effect = Exception("error")
        with self.assertRaises(IOError):
            self.cat.import_catalogue(zip_path)

    def test_import_catalogue_skips_files(self):
        # coverage for 431, 435-436, 443-444, 456-457
        zip_path = BACKUP_PATH / "cat.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("file_not_dir.txt", "x")
            zf.writestr("no_json_dir/file.txt", "x")
            zf.writestr("no_id_dir/" + self.settings.json_filename, '{"no_id": 1}')
            zf.writestr("bad_json_dir/" + self.settings.json_filename, 'invalid json')
            
        with self.assertLogs(level="WARNING") as cm:
            self.cat.import_catalogue(zip_path)
        log_out = " ".join(cm.output)
        self.assertIn("does not contain a snapshot json file", log_out)
        self.assertIn("snapshot ID is missing from json", log_out)
        self.assertIn("Failed to import snapshot", log_out)

    @patch('zipfile.ZipFile')
    def test_import_snapshot_exceptions(self, mock_zip):
        # coverage for 484-485
        mock_zip.side_effect = zipfile.BadZipFile("bad zip")
        zip_path = BACKUP_PATH / "fake2.zip"
        zip_path.touch()
        with self.assertRaises(ValueError):
            self.cat.import_snapshot(zip_path)
        
        mock_zip.side_effect = Exception("error")
        with self.assertRaises(IOError):
            self.cat.import_snapshot(zip_path)

    def test_import_snapshot_bad_json(self):
        # coverage for 494-495
        zip_path = BACKUP_PATH / "snap.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr(self.settings.json_filename, 'invalid json')
            
        with self.assertRaises(ValueError):
            self.cat.import_snapshot(zip_path)


if __name__ == "__main__":
    unittest.main()
