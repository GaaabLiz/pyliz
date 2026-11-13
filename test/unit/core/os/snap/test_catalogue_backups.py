"""Tests for listing and restoring snapshot backups."""

import json
import platform
import shutil
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from pylizlib.core.os.snap.catalogue import SnapshotCatalogue
from pylizlib.core.os.snap.domain import (
    BackupType,
    SnapshotSettings,
)
from pylizlib.core.os.snap.manager import SnapshotManager
from pylizlib.core.os.snap.operations.archives import SnapshotIncompleteError
from pylizlib.core.os.snap.operations.backup_manifest import BACKUP_MANIFEST_NAME
from pylizlib.core.os.snap.serializer import SnapshotSerializer
from pylizlib.core.os.snap.storage.transactions import SnapshotTransactionJournal, recover_pending_transactions, rename_and_sync
from test.support.snapshot import (
    BACKUP_PATH,
    CATALOGUE_PATH,
    SOURCE_DATA_PATH,
    TEST_LOCAL_ROOT,
    create_source_dirs,
    make_snapshot,
    setup_test_dirs,
    teardown_test_dirs,
)


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

    def test_restore_uses_configured_archive_staging_volume(self):
        from unittest.mock import patch

        from pylizlib.core.os.snap.storage.archives import extract_zip

        snap = make_snapshot("RestoreConfiguredTemp", self._src, n=1)
        self.cat.add(snap)
        manager = SnapshotManager(snap, CATALOGUE_PATH, self.settings)
        archive = manager.create_backup(BACKUP_PATH, "configured_temp", BackupType.ASSOCIATED_DIRECTORIES)
        configured_temp = TEST_LOCAL_ROOT / "restore_staging"
        self.settings.archive_temp_directory = configured_temp

        with patch("pylizlib.core.os.snap.operations.archives.extract_zip", wraps=extract_zip) as extract:
            self.cat.restore_backup(archive)

        extraction_root = extract.call_args.args[1]
        self.assertEqual(extraction_root.parent, configured_temp)
        self.assertTrue(extract.call_args.kwargs["additional_space_requirements"])

    def test_associated_restore_defaults_staging_to_a_target_volume(self):
        from unittest.mock import patch

        from pylizlib.core.os.snap.storage.archives import extract_zip

        snap = make_snapshot("RestoreTargetVolume", self._src, n=1)
        self.cat.add(snap)
        manager = SnapshotManager(snap, CATALOGUE_PATH, self.settings)
        archive = manager.create_backup(BACKUP_PATH, "target_volume", BackupType.ASSOCIATED_DIRECTORIES)
        destination = Path(snap.directories[0].original_path)

        with patch("pylizlib.core.os.snap.operations.archives.extract_zip", wraps=extract_zip) as extract:
            self.cat.restore_backup(archive)

        extraction_root = extract.call_args.args[1]
        self.assertEqual(extraction_root.parent, destination.parent)

    def test_associated_backup_contains_identity_path_and_index_manifest(self):
        snap = make_snapshot("RestoreADManifest", self._src, n=1)
        self.cat.add(snap)
        mgr = SnapshotManager(snap, CATALOGUE_PATH, self.settings)
        archive_path = mgr.create_backup(BACKUP_PATH, "manifest", BackupType.ASSOCIATED_DIRECTORIES)

        with zipfile.ZipFile(archive_path) as archive:
            manifest = json.loads(archive.read(BACKUP_MANIFEST_NAME))

        association = snap.directories[0]
        self.assertEqual(manifest["format"], "pyliz-snapshot-backup")
        self.assertEqual(manifest["version"], 1)
        self.assertEqual(manifest["backup_type"], "associated_directories")
        self.assertEqual(manifest["snapshot_id"], snap.id)
        self.assertEqual(manifest["os_created"], snap.os_created)
        self.assertEqual(manifest["prefix"], "manifest")
        self.assertTrue(manifest["created_at"])
        self.assertEqual(
            manifest["associations"],
            [
                {
                    "folder_id": association.folder_id,
                    "index": association.index,
                    "directory_name": association.directory_name,
                    "original_path": association.original_path,
                }
            ],
        )

    def test_associated_restore_uses_archived_mapping_after_current_metadata_changes(self):
        snap = make_snapshot("RestoreADMetadataChanged", self._src, n=1)
        self.cat.add(snap)
        mgr = SnapshotManager(snap, CATALOGUE_PATH, self.settings)
        archive_path = mgr.create_backup(BACKUP_PATH, "captured", BackupType.ASSOCIATED_DIRECTORIES)
        association = snap.directories[0]
        original_path = Path(association.original_path)
        archived_file = original_path / "br1_file.txt"
        archived_content = archived_file.read_text()

        changed_path = TEST_LOCAL_ROOT / "association_moved_after_backup"
        changed_path.mkdir()
        (changed_path / "current.txt").write_text("current metadata destination")
        association.index = 8
        association.original_path = str(changed_path)
        association._set_storage_name("renamed_storage_after_backup")
        SnapshotSerializer.to_json(snap, mgr.path_snapshot_json)
        archived_file.write_text("live directory changed")

        self.cat.restore_backup(archive_path)

        self.assertEqual(archived_file.read_text(), archived_content)
        self.assertEqual((changed_path / "current.txt").read_text(), "current metadata destination")
        self.assertFalse((changed_path / "br1_file.txt").exists())

    def test_restore_backup_raises_on_unknown_type(self):
        unknown_zip = BACKUP_PATH / "unknown_backup.zip"
        with zipfile.ZipFile(unknown_zip, "w") as zf:
            zf.writestr("dummy.txt", "x")
        with self.assertRaises(ValueError):
            self.cat.restore_backup(unknown_zip)

    def test_restore_backup_ad_is_self_contained_when_snapshot_missing(self):
        snap = make_snapshot("RestoreADMissing", self._src, n=1)
        snap.id = "snap_123"
        self.cat.add(snap)
        mgr = SnapshotManager(snap, CATALOGUE_PATH, self.settings)
        original_archive = mgr.create_backup(BACKUP_PATH, "preinstall", BackupType.ASSOCIATED_DIRECTORIES)
        backup_zip = BACKUP_PATH / "renamed_snapshot_directory_sd.backup"
        original_archive.rename(backup_zip)
        target_file = Path(snap.directories[0].original_path) / "br1_file.txt"
        original_content = target_file.read_text()
        shutil.rmtree(CATALOGUE_PATH / snap.id)
        target_file.write_text("changed after backup")

        self.cat.restore_backup(backup_zip)

        self.assertEqual(target_file.read_text(), original_content)
        self.assertFalse((CATALOGUE_PATH / snap.id).exists())
        self.assertFalse((CATALOGUE_PATH / ".pyliz_transactions").exists())

    def test_snapshot_backup_type_and_identity_survive_rename(self):
        snap = make_snapshot("RestoreSDRenamed", self._src, n=1)
        snap.id = "snapshot_123"
        self.cat.add(snap)
        mgr = SnapshotManager(snap, CATALOGUE_PATH, self.settings)
        original_archive = mgr.create_backup(BACKUP_PATH, "beforeDelete", BackupType.SNAPSHOT_DIRECTORY)
        with zipfile.ZipFile(original_archive) as archive:
            manifest = json.loads(archive.read(BACKUP_MANIFEST_NAME))
        self.assertEqual(manifest["version"], 1)
        self.assertEqual(manifest["backup_type"], "snapshot_directory")
        self.assertEqual(manifest["snapshot_id"], "snapshot_123")
        self.assertEqual(manifest["associations"][0]["folder_id"], snap.directories[0].folder_id)
        renamed_archive = BACKUP_PATH / "renamed_associated_directories_ad.backup"
        original_archive.rename(renamed_archive)
        shutil.rmtree(CATALOGUE_PATH / snap.id)

        listed = next(info for info in self.cat.list_backups(BACKUP_PATH) if info.file_name == renamed_archive.name)
        self.assertEqual(listed.snapshot_id, "snapshot_123")
        self.assertEqual(listed.backup_type, BackupType.SNAPSHOT_DIRECTORY)

        self.cat.restore_backup(renamed_archive)

        restored = self.cat.get_by_id("snapshot_123")
        self.assertIsNotNone(restored)
        self.assertFalse((CATALOGUE_PATH / snap.id / BACKUP_MANIFEST_NAME).exists())

    def test_restore_backup_ad_can_remap_destinations_by_association_id(self):
        snap = make_snapshot("RestoreADMapped", self._src, n=1)
        self.cat.add(snap)
        mgr = SnapshotManager(snap, CATALOGUE_PATH, self.settings)
        backup_zip = mgr.create_backup(BACKUP_PATH, "mapped", BackupType.ASSOCIATED_DIRECTORIES)
        source = Path(snap.directories[0].original_path)
        source_file = source / "br1_file.txt"
        archived_content = source_file.read_text()
        source_file.write_text("keep the moved source unchanged")
        shutil.rmtree(CATALOGUE_PATH / snap.id)

        destination = TEST_LOCAL_ROOT / "mapped_associated_directory"
        destination.mkdir()
        (destination / "old.txt").write_text("replace this directory")
        self.cat.restore_backup_with_mapping(backup_zip, {snap.directories[0].folder_id: destination})

        self.assertEqual((destination / "br1_file.txt").read_text(), archived_content)
        self.assertFalse((destination / "old.txt").exists())
        self.assertEqual(source_file.read_text(), "keep the moved source unchanged")
        self.assertFalse((CATALOGUE_PATH / snap.id).exists())

    def test_restore_backup_ad_rejects_critical_and_catalogue_destinations(self):
        snap = make_snapshot("RestoreADUnsafeDestination", self._src, n=1)
        self.cat.add(snap)
        mgr = SnapshotManager(snap, CATALOGUE_PATH, self.settings)
        backup_zip = mgr.create_backup(BACKUP_PATH, "unsafe_destination", BackupType.ASSOCIATED_DIRECTORIES)
        source_file = Path(snap.directories[0].original_path) / "br1_file.txt"
        original_content = source_file.read_text()
        association_id = snap.directories[0].folder_id

        for destination in (Path("/usr/bin"), CATALOGUE_PATH):
            with self.subTest(destination=destination):
                with self.assertRaises(ValueError):
                    self.cat.restore_backup_with_mapping(backup_zip, {association_id: destination})

        self.assertEqual(source_file.read_text(), original_content)
        self.assertFalse((CATALOGUE_PATH / ".pyliz_transactions").exists())

    def test_restore_backup_ad_rejects_a_different_origin_operating_system(self):
        snap = make_snapshot("RestoreADOtherOS", self._src, n=1)
        snap.os_created = "DifferentOS"
        self.cat.add(snap)
        mgr = SnapshotManager(snap, CATALOGUE_PATH, self.settings)
        backup_zip = mgr.create_backup(BACKUP_PATH, "other_os", BackupType.ASSOCIATED_DIRECTORIES)
        source_file = Path(snap.directories[0].original_path) / "br1_file.txt"
        original_content = source_file.read_text()

        with self.assertRaisesRegex(RuntimeError, f"current OS is {platform.system()}"):
            self.cat.restore_backup(backup_zip)

        self.assertEqual(source_file.read_text(), original_content)
        self.assertFalse((CATALOGUE_PATH / ".pyliz_transactions").exists())

    def test_standalone_associated_restore_journal_recovers_an_interrupted_swap(self):
        destination = TEST_LOCAL_ROOT / "standalone_restore_recovery"
        destination.mkdir()
        (destination / "old.txt").write_text("old data")
        journal = SnapshotTransactionJournal.begin(CATALOGUE_PATH, "restore_associations_manifest", {"entries": []})
        staged = destination.with_name(f"{destination.name}_staging_crash")
        staged.mkdir()
        (staged / "new.txt").write_text("new data")
        backup = destination.with_name(f"{destination.name}_bck_crash")
        journal.update_payload(
            entries=[
                {
                    "folder_id": "crash-association",
                    "stage": staged.as_posix(),
                    "destination": destination.as_posix(),
                    "backup": backup.as_posix(),
                    "had_original": True,
                }
            ]
        )
        rename_and_sync(destination, backup)

        recovered = recover_pending_transactions(CATALOGUE_PATH)

        self.assertEqual(recovered, ["restore_associations_manifest"])
        self.assertEqual((destination / "old.txt").read_text(), "old data")
        self.assertFalse((destination / "new.txt").exists())
        self.assertFalse((CATALOGUE_PATH / ".pyliz_transactions").exists())


class TestSnapshotCatalogueBackupFailurePaths(unittest.TestCase):
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

    @patch("zipfile.ZipFile")
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

    def test_restore_backup_sd_preserves_original_when_rename_fails(self):
        snap = make_snapshot("RestoreSDRenameFail", self._src, n=1)
        self.cat.add(snap)
        mgr = SnapshotManager(snap, CATALOGUE_PATH, self.settings)
        mgr.create_backup(BACKUP_PATH, "bck", BackupType.SNAPSHOT_DIRECTORY)
        backup_zip = next(BACKUP_PATH.glob("*_*_sd_*.zip"))
        dest = CATALOGUE_PATH / snap.id
        (dest / "original_only.txt").write_text("must survive")
        original_files = {p.relative_to(dest): p.read_bytes() for p in dest.rglob("*") if p.is_file()}
        rename_error = PermissionError("snapshot directory is busy")

        with patch.object(Path, "rename", side_effect=rename_error) as mock_rename:
            with self.assertRaisesRegex(IOError, "Failed to restore snapshot directory") as ctx:
                self.cat.restore_backup(backup_zip)

        self.assertIs(ctx.exception.__cause__, rename_error)
        mock_rename.assert_called_once()
        self.assertTrue(dest.is_dir())
        self.assertEqual({p.relative_to(dest): p.read_bytes() for p in dest.rglob("*") if p.is_file()}, original_files)
        self.assertEqual(set(CATALOGUE_PATH.iterdir()), {dest, CATALOGUE_PATH / ".pyliz_snapshot.lock"})

    def test_restore_backup_sd_cleans_partial_copy_on_error(self):
        snap = make_snapshot("RestoreSDPartialFail", self._src, n=1)
        self.cat.add(snap)
        mgr = SnapshotManager(snap, CATALOGUE_PATH, self.settings)
        mgr.create_backup(BACKUP_PATH, "bck", BackupType.SNAPSHOT_DIRECTORY)
        backup_zip = next(BACKUP_PATH.glob("*_*_sd_*.zip"))
        dest = CATALOGUE_PATH / snap.id
        (dest / "original_only.txt").write_text("must survive")
        original_files = {p.relative_to(dest): p.read_bytes() for p in dest.rglob("*") if p.is_file()}

        def fail_partial_copy(source, destination, **kwargs):
            destination.mkdir(exist_ok=True)
            (destination / "partial.txt").write_text("incomplete copy")
            raise OSError("copy interrupted")

        for destination_exists in (True, False):
            with self.subTest(destination_exists=destination_exists):
                if not destination_exists:
                    shutil.rmtree(dest)
                with patch("shutil.copytree", side_effect=fail_partial_copy):
                    with self.assertRaisesRegex(IOError, "Failed to restore snapshot directory"):
                        self.cat.restore_backup(backup_zip)

                if destination_exists:
                    self.assertEqual({p.relative_to(dest): p.read_bytes() for p in dest.rglob("*") if p.is_file()}, original_files)
                    self.assertEqual(set(CATALOGUE_PATH.iterdir()), {dest, CATALOGUE_PATH / ".pyliz_snapshot.lock"})
                else:
                    self.assertFalse(dest.exists())
                    self.assertEqual(list(CATALOGUE_PATH.iterdir()), [CATALOGUE_PATH / ".pyliz_snapshot.lock"])

    @patch("shutil.copytree")
    def test_restore_backup_sd_rolls_back_on_error(self, mock_copytree):
        snap = make_snapshot("RestoreSDFail", self._src, n=1)
        self.cat.add(snap)
        mgr = SnapshotManager(snap, CATALOGUE_PATH, self.settings)
        mgr.create_backup(BACKUP_PATH, "bck", BackupType.SNAPSHOT_DIRECTORY)
        backup_zip = sorted(BACKUP_PATH.glob("*_*_sd_*.zip"))[-1]

        # Put something in the snapshot directory to verify rollback
        dest = CATALOGUE_PATH / snap.id
        (dest / "old_file.txt").write_text("should_stay")

        mock_copytree.side_effect = Exception("simulated copy failure")

        with self.assertRaises(IOError) as ctx:
            self.cat.restore_backup(backup_zip)
        self.assertIn("Failed to restore snapshot directory", str(ctx.exception))

        self.assertTrue((dest / "old_file.txt").exists())
        self.assertEqual((dest / "old_file.txt").read_text(), "should_stay")

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
        with self.assertRaises(SnapshotIncompleteError) as ctx:
            self.cat.restore_backup(zip_path)
        self.assertEqual(ctx.exception.missing_folders, [snap.directories[0].original_path])
        self.assertEqual(ctx.exception.unexpected_entries, ["dummy.txt"])

    def test_restore_backup_ad_unmatched_dir(self):
        # coverage for 191-194
        snap = make_snapshot("RestoreADUnmatch", self._src, n=1)
        self.cat.add(snap)

        zip_path = BACKUP_PATH / f"backup_pref_{snap.id}_ad_20230101_120000.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("unmatched_dir/file.txt", "x")

        with self.assertRaises(SnapshotIncompleteError) as ctx:
            self.cat.restore_backup(zip_path)
        self.assertEqual(ctx.exception.missing_folders, [snap.directories[0].original_path])
        self.assertEqual(ctx.exception.unexpected_entries, ["unmatched_dir"])

    def test_restore_backup_ad_reports_missing_associations_before_modifying_destinations(self):
        sources = create_source_dirs(SOURCE_DATA_PATH, ["partial_restore_one", "partial_restore_two"])
        snap = make_snapshot("RestoreADIncomplete", sources, n=2)
        self.cat.add(snap)
        destinations = [Path(association.original_path) for association in snap.directories]
        for index, destination in enumerate(destinations):
            (destination / "keep.txt").write_text(f"original {index}")

        zip_path = BACKUP_PATH / f"backup_pref_{snap.id}_ad_20230101_120000.zip"
        present_association = snap.directories[0]
        with zipfile.ZipFile(zip_path, "w") as archive:
            archive.writestr(f"{present_association.directory_name}/", "")
            archive.writestr(f"{present_association.directory_name}/replacement.txt", "archive data")

        with self.assertRaises(SnapshotIncompleteError) as ctx:
            self.cat.restore_backup(zip_path)

        self.assertEqual(ctx.exception.missing_folders, [snap.directories[1].original_path])
        self.assertEqual(ctx.exception.unexpected_entries, [])
        for index, destination in enumerate(destinations):
            self.assertEqual((destination / "keep.txt").read_text(), f"original {index}")
            self.assertFalse((destination / "replacement.txt").exists())

    def test_restore_backup_ad_restore_items(self):
        # coverage for 206, 213, 220
        snap = make_snapshot("RestoreADItems", self._src, n=1)
        self.cat.add(snap)
        zip_path = BACKUP_PATH / f"backup_pref_{snap.id}_ad_20230101_120000.zip"

        dir_name = snap.directories[0].directory_name
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
        self.assertFalse((dest / "old_file.txt").exists())

    def test_restore_backup_ad_rolls_back_on_error(self):
        snap = make_snapshot("RestoreADFail", self._src, n=1)
        self.cat.add(snap)
        zip_path = BACKUP_PATH / f"backup_pref_{snap.id}_ad_20230101_120000.zip"

        dir_name = snap.directories[0].directory_name
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr(f"{dir_name}/file.txt", "x")

        dest = Path(snap.directories[0].original_path)
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "old_file.txt").write_text("should_stay")

        with patch.object(self.settings.copy_strategy, "copy_directory", side_effect=Exception("simulated failure")):
            with self.assertRaises(IOError) as ctx:
                self.cat.restore_backup(zip_path)
        self.assertIn("Failed to restore associated directories", str(ctx.exception))

        # The rollback should have restored old_file.txt
        self.assertTrue((dest / "old_file.txt").exists())
        self.assertEqual((dest / "old_file.txt").read_text(), "should_stay")
