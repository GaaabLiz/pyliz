"""Tests for creating snapshot and association backups."""

import errno
import os
import shutil
import zipfile
from pathlib import Path
from unittest.mock import patch

from pylizlib.core.os.snap.domain import (
    BackupType,
    SnapDirAssociation,
    Snapshot,
    SnapshotSettings,
)
from pylizlib.core.os.snap.manager import SnapshotManager
from pylizlib.core.os.snap.operations.archives import SnapshotIncompleteError
from test.support.snapshot import (
    BACKUP_PATH,
    CATALOGUE_PATH,
    SOURCE_DATA_PATH,
    TEST_LOCAL_ROOT,
    SnapshotManagerTestHelper,
    create_source_dirs,
    make_snapshot,
    setup_test_dirs,
    teardown_test_dirs,
)


class TestSnapshotManagerBackups(SnapshotManagerTestHelper):
    def setUp(self):
        setup_test_dirs()
        self._src = create_source_dirs(SOURCE_DATA_PATH, ["ab1", "ab2", "ab3"])

    def tearDown(self):
        teardown_test_dirs()

    def test_create_backup_snapshot_directory(self):
        snap = make_snapshot("BckSnap", self._src, n=1)
        mgr = self._mgr(snap)
        mgr.create()
        result = mgr.create_backup(BACKUP_PATH, "test_prefix", BackupType.SNAPSHOT_DIRECTORY)
        zips = list(BACKUP_PATH.glob("*.zip"))
        self.assertEqual(len(zips), 1)
        self.assertEqual(result, zips[0])
        self.assertIn("test_prefix", zips[0].name)

        with zipfile.ZipFile(zips[0]) as zf:
            names = zf.namelist()
        self.assertTrue(any("snapshot.json" in n for n in names))

    def test_snapshot_backup_rejects_destination_inside_snapshot(self):
        snap = make_snapshot("BackupInsideSnapshot", self._src, n=1)
        mgr = self._mgr(snap)
        mgr.create()
        backup_path = mgr.path_snapshot / "backups"

        with self.assertRaisesRegex(ValueError, "inside archived source"):
            mgr.create_backup(backup_path, "nested", BackupType.SNAPSHOT_DIRECTORY)

        self.assertFalse(backup_path.exists())

    def test_associated_backup_rejects_destination_inside_source(self):
        snap = make_snapshot("BackupInsideSource", self._src, n=1)
        mgr = self._mgr(snap)
        mgr.create()
        backup_path = self._src[0] / "backups"

        with self.assertRaisesRegex(ValueError, "inside archived source"):
            mgr.create_backup(backup_path, "nested", BackupType.ASSOCIATED_DIRECTORIES)

        self.assertFalse(backup_path.exists())

    def test_associated_backup_rejects_destination_inside_symlink_alias(self):
        snap = make_snapshot("BackupInsideSourceAlias", self._src, n=1)
        mgr = self._mgr(snap)
        mgr.create()
        alias = TEST_LOCAL_ROOT / "backup_source_alias"
        try:
            alias.symlink_to(self._src[0], target_is_directory=True)
        except OSError as error:
            self.skipTest(f"Directory symlinks are unavailable: {error}")
        backup_path = alias / "backups"

        with self.assertRaisesRegex(ValueError, "inside archived source"):
            mgr.create_backup(backup_path, "nested_alias", BackupType.ASSOCIATED_DIRECTORIES)

        self.assertFalse((self._src[0] / "backups").exists())

    def test_associated_directory_backup_preserves_empty_association_root(self):
        source = SOURCE_DATA_PATH / "empty_backup" / "nested_empty"
        source.mkdir(parents=True)
        snap = Snapshot(
            id="EmptyAssocBackup",
            name="Empty association backup",
            desc="",
            directories=[SnapDirAssociation(index=1, original_path=str(source.parent), folder_id="empty-backup")],
        )
        mgr = self._mgr(snap)
        mgr.create()

        archive_path = mgr.create_backup(BACKUP_PATH, "empty_association", BackupType.ASSOCIATED_DIRECTORIES)
        with zipfile.ZipFile(archive_path) as archive:
            names = archive.namelist()
        association_root = snap.directories[0].directory_name
        self.assertIn(f"{association_root}/", names)
        self.assertIn(f"{association_root}/nested_empty/", names)

    def test_associated_directory_backup_rejects_links_instead_of_skipping_or_following_them(self):
        snap = make_snapshot("AssociatedBackupLinks", self._src, n=1)
        mgr = self._mgr(snap)
        mgr.create()

        outside = TEST_LOCAL_ROOT / "associated_backup_link_target"
        outside.mkdir()
        important = outside / "important.txt"
        important.write_text("keep me", encoding="utf-8")
        link = self._src[0] / "linked-directory"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"Directory symlinks are unavailable: {error}")

        with self.assertRaisesRegex(ValueError, "symbolic link"):
            mgr.create_backup(BACKUP_PATH, "associated_links", BackupType.ASSOCIATED_DIRECTORIES)

        self.assertEqual(important.read_text(encoding="utf-8"), "keep me")
        self.assertEqual(list(BACKUP_PATH.glob("*.zip")), [])

    def test_associated_directory_backup_reports_missing_or_non_directory_sources_without_publishing(self):
        snap = make_snapshot("MissingAssocBackup", self._src[:2], n=2)
        mgr = self._mgr(snap)
        mgr.create()
        expected_missing = [association.original_path for association in snap.directories]
        shutil.rmtree(self._src[0])
        self._src[0].write_text("not a directory")
        shutil.rmtree(self._src[1])

        with self.assertRaises(SnapshotIncompleteError) as ctx:
            mgr.create_backup(BACKUP_PATH, "missing_association", BackupType.ASSOCIATED_DIRECTORIES)

        self.assertEqual(ctx.exception.missing_folders, expected_missing)
        self.assertEqual(ctx.exception.unexpected_entries, [])
        self.assertEqual(list(BACKUP_PATH.glob("*.zip")), [])

    def test_failed_backup_preserves_existing_archive_and_removes_partial_file(self):
        snap = make_snapshot("AtomicBackup", self._src, n=1)
        mgr = self._mgr(snap)
        mgr.create()
        real_write = zipfile.ZipFile.write

        def fail_after_write(archive, *args, **kwargs):
            real_write(archive, *args, **kwargs)
            raise OSError("backup write interrupted")

        with patch("pylizlib.core.os.snap.operations.archives.datetime") as mock_datetime:
            mock_datetime.now.return_value.strftime.return_value = "20261105_120000"
            mgr.create_backup(BACKUP_PATH, "atomic", BackupType.SNAPSHOT_DIRECTORY)
            published = next(BACKUP_PATH.glob("*.zip"))
            original_bytes = published.read_bytes()

            with patch.object(zipfile.ZipFile, "write", autospec=True, side_effect=fail_after_write):
                with self.assertRaisesRegex(OSError, "backup write interrupted"):
                    mgr.create_backup(BACKUP_PATH, "atomic", BackupType.SNAPSHOT_DIRECTORY)

        self.assertEqual(published.read_bytes(), original_bytes)
        self.assertEqual(list(BACKUP_PATH.iterdir()), [published])

    def test_create_backup_same_second_preserves_previous_archive(self):
        snap = make_snapshot("BackupNameCollision", self._src, n=1)
        mgr = self._mgr(snap)
        mgr.create()

        with patch("pylizlib.core.os.snap.operations.archives.datetime") as mock_datetime:
            mock_datetime.now.return_value.strftime.return_value = "20261105_120000"
            first = mgr.create_backup(BACKUP_PATH, "same_second", BackupType.SNAPSHOT_DIRECTORY)
            first_bytes = first.read_bytes()
            new_content = mgr.path_snapshot / "created_after_first_backup.txt"
            new_content.write_text("second backup data")
            second = mgr.create_backup(BACKUP_PATH, "same_second", BackupType.SNAPSHOT_DIRECTORY)

        self.assertNotEqual(first, second)
        self.assertTrue(second.name.endswith("_20261105_120000_1.zip"))
        self.assertEqual(first.read_bytes(), first_bytes)
        with zipfile.ZipFile(second) as archive:
            self.assertEqual(archive.read("created_after_first_backup.txt"), b"second backup data")

        from pylizlib.core.os.snap.operations.backup_names import parse_backup_filename

        parsed = parse_backup_filename(second)
        self.assertEqual(parsed.snapshot_id, snap.id)
        self.assertEqual(parsed.prefix, "same_second")
        self.assertEqual(parsed.backup_type, BackupType.SNAPSHOT_DIRECTORY)
        self.assertEqual(parsed.created_at.strftime("%Y%m%d_%H%M%S"), "20261105_120000")

    def test_backup_validation_failure_prevents_publication(self):
        snap = make_snapshot("InvalidBackup", self._src, n=1)
        mgr = self._mgr(snap)
        mgr.create()

        with patch.object(zipfile.ZipFile, "testzip", return_value="corrupted.txt"):
            with self.assertRaises(zipfile.BadZipFile):
                mgr.create_backup(BACKUP_PATH, "invalid", BackupType.SNAPSHOT_DIRECTORY)

        self.assertEqual(list(BACKUP_PATH.iterdir()), [])

    def test_backup_publication_failure_removes_partial_file(self):
        snap = make_snapshot("BackupPublishFail", self._src, n=1)
        mgr = self._mgr(snap)
        mgr.create()

        with patch.object(Path, "hardlink_to", side_effect=PermissionError("backup publication denied")):
            with self.assertRaisesRegex(PermissionError, "backup publication denied"):
                mgr.create_backup(BACKUP_PATH, "unpublished", BackupType.SNAPSHOT_DIRECTORY)

        self.assertEqual(list(BACKUP_PATH.iterdir()), [])

    def test_backup_scan_errors_prevent_publication(self):
        nested = self._src[0] / "nested"
        nested.mkdir()
        (nested / "important.txt").write_text("must be backed up")
        snap = make_snapshot("ScanFailure", self._src, n=1)
        mgr = self._mgr(snap)
        mgr.create()
        real_scandir = os.scandir

        for backup_type in BackupType:
            root = self._src[0] if backup_type == BackupType.ASSOCIATED_DIRECTORIES else mgr.path_snapshot
            for blocked in (root, root / "nested" if root == self._src[0] else root / snap.directories[0].directory_name / "nested"):
                for error in (PermissionError(errno.EACCES, "scan denied", str(blocked)), OSError(errno.EIO, "scan failed", str(blocked))):
                    with self.subTest(backup_type=backup_type, blocked=blocked, error=error):

                        def fail_scan(path):
                            if Path(path) == blocked:
                                raise error
                            return real_scandir(path)

                        with patch("os.scandir", side_effect=fail_scan):
                            with self.assertRaises(OSError) as ctx:
                                mgr.create_backup(BACKUP_PATH, "scan", backup_type)

                        self.assertIs(ctx.exception, error)
                        self.assertEqual(list(BACKUP_PATH.iterdir()), [])

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


class TestSnapshotManagerBackupFailurePaths(SnapshotManagerTestHelper):
    def setUp(self):
        setup_test_dirs()
        self._src = create_source_dirs(SOURCE_DATA_PATH, ["cov1"])

    def tearDown(self):
        teardown_test_dirs()

    def test_create_backup_exceptions(self):
        # coverage 371-372
        snap = make_snapshot("BackupExceptions", self._src, n=1)
        mgr = SnapshotManager(snap, CATALOGUE_PATH, SnapshotSettings())
        mgr.create()
        with patch("zipfile.ZipFile", side_effect=RuntimeError("zip error")):
            with self.assertLogs(level="ERROR") as cm:
                with self.assertRaisesRegex(RuntimeError, "zip error"):
                    mgr.create_backup(BACKUP_PATH, "pref", BackupType.SNAPSHOT_DIRECTORY)
            self.assertIn("zip error", " ".join(cm.output))
