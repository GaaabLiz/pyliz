"""Tests for snapshot and catalogue ZIP import and export."""

import errno
import os
import shutil
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from pylizlib.core.os.snap.catalogue import SnapshotCatalogue
from pylizlib.core.os.snap.domain import (
    SnapDirAssociation,
    Snapshot,
    SnapshotSettings,
)
from pylizlib.core.os.snap.operations.backup_manifest import BACKUP_MANIFEST_NAME
from pylizlib.core.os.snap.serializer import SnapshotSerializer
from test.core.os.snap.conftest import (
    BACKUP_PATH,
    CATALOGUE_PATH,
    SOURCE_DATA_PATH,
    TEST_LOCAL_ROOT,
    create_source_dirs,
    make_snapshot,
    setup_test_dirs,
    teardown_test_dirs,
)
from test.core.os.snap.conftest import (
    make_catalogue as _cat,
)


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
        self.assertFalse((CATALOGUE_PATH / snap.id / BACKUP_MANIFEST_NAME).exists())

    def test_import_snapshot_uses_configured_staging_volume(self):
        from unittest.mock import patch

        from pylizlib.core.os.snap.storage.publication import publish_snapshot_tree

        snap = make_snapshot("ImportConfiguredTemp", self._src, n=1)
        self.cat.add(snap)
        self.cat.export_snapshot(snap.id, self._export_dir)
        archive = next(self._export_dir.glob("*.zip"))
        self.cat.delete(snap)
        configured_temp = TEST_LOCAL_ROOT / "archive_staging"
        self.cat.settings.archive_temp_directory = configured_temp

        with patch(
            "pylizlib.core.os.snap.operations.transfers.publish_snapshot_tree",
            wraps=publish_snapshot_tree,
        ) as publish:
            self.cat.import_snapshot(archive)

        extracted_root = publish.call_args.args[0]
        self.assertEqual(extracted_root.parent, configured_temp)
        self.assertTrue(self.cat.exists(snap.id))

    def test_import_snapshot_enforces_configured_archive_entry_limit(self):
        snap = make_snapshot("ImportEntryLimit", self._src, n=1)
        self.cat.add(snap)
        self.cat.export_snapshot(snap.id, self._export_dir)
        archive = next(self._export_dir.glob("*.zip"))
        self.cat.delete(snap)
        self.cat.settings.max_archive_entries = 0

        with self.assertRaisesRegex(ValueError, "configured limit is 0"):
            self.cat.import_snapshot(archive)

        self.assertFalse(self.cat.exists(snap.id))

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

    def test_import_snapshot_does_not_publish_staging_missing_an_association(self):
        from pylizlib.core.os.snap.copy_strategy import DirectoryCopyStrategy, SequentialFileCopyStrategy

        class MetadataOnlyStrategy(DirectoryCopyStrategy):
            """Return a copy that silently omitted an association directory."""

            def copy_directory(self, source, destination, progress_callback=None, message_callback=None, *, manifest=None, expected_manifest=None):
                """Copy only metadata to expose incomplete staging validation."""
                destination.mkdir(parents=True)
                shutil.copy2(Path(source) / "snapshot.json", Path(destination) / "snapshot.json")
                return Path(destination)

        snap = make_snapshot("IncompleteImport", self._src, n=1)
        self.cat.add(snap)
        self.cat.export_snapshot(snap.id, self._export_dir)
        archive = next(self._export_dir.glob("*.zip"))
        self.cat.delete(snap)
        self.cat.settings.copy_strategy = MetadataOnlyStrategy()

        with self.assertRaisesRegex(FileNotFoundError, "association directory"):
            self.cat.import_snapshot(archive)

        destination = CATALOGUE_PATH / snap.id
        self.assertFalse(destination.exists())
        self.assertFalse(self.cat.exists(snap.id))

        self.cat.settings.copy_strategy = SequentialFileCopyStrategy()
        self.cat.import_snapshot(archive)
        self.assertTrue(self.cat.exists(snap.id))
        imported = self.cat.get_by_id(snap.id)
        self.assertTrue((destination / imported.directories[0].directory_name / "ie1_file.txt").is_file())

    def test_catalogue_import_failure_after_metadata_copy_leaves_no_conflicting_entry(self):
        from pylizlib.core.os.snap.copy_strategy import DirectoryCopyStrategy, SequentialFileCopyStrategy

        class FailAfterMetadataStrategy(DirectoryCopyStrategy):
            """Copy the visible metadata and fail before any payload is copied."""

            def copy_directory(self, source, destination, progress_callback=None, message_callback=None, *, manifest=None, expected_manifest=None):
                """Leave an incomplete staging tree, then simulate an I/O error."""
                destination.mkdir(parents=True)
                shutil.copy2(Path(source) / "snapshot.json", Path(destination) / "snapshot.json")
                raise OSError("payload copy interrupted")

        source = TEST_LOCAL_ROOT / "partial_catalogue_entry"
        source.mkdir()
        SnapshotSerializer.to_json(Snapshot("partial-import", "Partial import", ""), source / "snapshot.json")
        (source / "important.bin").write_bytes(b"payload")
        archive = self._export_dir / "partial_catalogue.zip"
        with zipfile.ZipFile(archive, "w") as output:
            output.write(source / "snapshot.json", "partial-import/snapshot.json")
            output.write(source / "important.bin", "partial-import/important.bin")

        self.cat.settings.copy_strategy = FailAfterMetadataStrategy()
        self.cat.import_catalogue(archive)
        destination = CATALOGUE_PATH / "partial-import"
        self.assertFalse(destination.exists())
        self.assertFalse(self.cat.exists("partial-import"))

        self.cat.settings.copy_strategy = SequentialFileCopyStrategy()
        self.cat.import_catalogue(archive)
        self.assertTrue(self.cat.exists("partial-import"))
        self.assertEqual((destination / "important.bin").read_bytes(), b"payload")

    def test_export_and_import_full_catalogue(self):
        for i in range(3):
            self.cat.add(make_snapshot(f"CatExp{i}", self._src, n=1))

        with patch.object(SnapshotSerializer, "from_json", wraps=SnapshotSerializer.from_json) as read_metadata:
            self.cat.export_catalogue(self._export_dir, "cat.zip")
        self.assertEqual(read_metadata.call_count, 3)
        self.assertTrue((self._export_dir / "cat.zip").exists())

        for s in self.cat.get_all():
            self.cat.delete(s)
        self.assertEqual(len(self.cat.get_all()), 0)
        self.cat.import_catalogue(self._export_dir / "cat.zip")
        self.assertEqual(len(self.cat.get_all()), 3)

    def test_catalogue_round_trip_preserves_empty_association_directories(self):
        source = SOURCE_DATA_PATH / "empty_association"
        nested = source / "empty_child" / "empty_grandchild"
        nested.mkdir(parents=True)
        association = SnapDirAssociation(index=1, original_path=str(source), folder_id="empty-assoc")
        snapshot = Snapshot("EmptyAssociation", "Empty association", "", directories=[association])
        self.cat.add(snapshot)
        shutil.rmtree(source)

        self.cat.export_catalogue(self._export_dir, "empty-association.zip")
        archive_path = self._export_dir / "empty-association.zip"
        with zipfile.ZipFile(archive_path) as archive:
            names = archive.namelist()
        self.assertIn(f"{snapshot.id}/{association.directory_name}/", names)
        self.assertIn(f"{snapshot.id}/{association.directory_name}/empty_child/", names)
        self.assertIn(f"{snapshot.id}/{association.directory_name}/empty_child/empty_grandchild/", names)

        self.cat.delete(snapshot)
        self.cat.import_catalogue(archive_path)
        imported = self.cat.get_by_id(snapshot.id)
        imported_root = CATALOGUE_PATH / imported.id / imported.directories[0].directory_name
        self.assertTrue((imported_root / "empty_child" / "empty_grandchild").is_dir())

        self.cat.install(imported)
        self.assertTrue((source / "empty_child" / "empty_grandchild").is_dir())

    def test_export_catalogue_scan_failure_does_not_publish_incomplete_zip(self):
        nested = self._src[0] / "nested"
        nested.mkdir()
        (nested / "important.txt").write_text("must be exported")
        snap = make_snapshot("ExportScanFailure", self._src, n=1)
        self.cat.add(snap)
        self.cat.export_catalogue(self._export_dir, "existing.zip")
        existing = self._export_dir / "existing.zip"
        before = existing.read_bytes()
        blocked = CATALOGUE_PATH / snap.id / snap.directories[0].directory_name / "nested"
        real_scandir = os.scandir

        def fail_scan(path):
            if Path(path) == blocked:
                raise PermissionError(errno.EACCES, "scan denied", str(blocked))
            return real_scandir(path)

        for file_name in ("existing.zip", "new.zip"):
            with self.subTest(file_name=file_name):
                with patch("os.scandir", side_effect=fail_scan):
                    with self.assertRaises(PermissionError):
                        self.cat.export_catalogue(self._export_dir, file_name)

                self.assertEqual(existing.read_bytes(), before)
                self.assertEqual(list(self._export_dir.iterdir()), [existing])

    def test_export_catalogue_rejects_symlinked_tree_entries(self):
        snap = make_snapshot("ExportSymlink", self._src, n=1)
        self.cat.add(snap)

        outside = TEST_LOCAL_ROOT / "catalogue_export_link_target"
        outside.mkdir()
        important = outside / "important.txt"
        important.write_text("keep me", encoding="utf-8")
        stored_copy = CATALOGUE_PATH / snap.id / snap.directories[0].directory_name
        link = stored_copy / "linked-directory"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"Directory symlinks are unavailable: {error}")

        archive_path = self._export_dir / "linked-catalogue.zip"
        with self.assertRaisesRegex(ValueError, "symbolic link"):
            self.cat.export_catalogue(self._export_dir, archive_path.name)

        self.assertFalse(archive_path.exists())
        self.assertEqual(list(self._export_dir.iterdir()), [])
        self.assertEqual(important.read_text(encoding="utf-8"), "keep me")

    def test_export_catalogue_propagates_metadata_read_errors(self):
        snap = make_snapshot("UnreadableExportMetadata", self._src, n=1)
        self.cat.add(snap)

        with patch("pylizlib.core.os.snap.serializer.SnapshotSerializer.from_json", side_effect=OSError(errno.EIO, "metadata read failed")):
            with self.assertRaisesRegex(OSError, "metadata read failed"):
                self.cat.export_catalogue(self._export_dir)

        self.assertEqual(list(self._export_dir.iterdir()), [])

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


class TestSnapshotCatalogueTransferFailurePaths(unittest.TestCase):
    def setUp(self):
        setup_test_dirs()
        self._src = create_source_dirs(SOURCE_DATA_PATH, ["cov1"])
        self.settings = SnapshotSettings(backup_path=BACKUP_PATH)
        self.cat = SnapshotCatalogue(CATALOGUE_PATH, settings=self.settings)

    def tearDown(self):
        teardown_test_dirs()

    def test_import_catalogue_invalid_path(self):
        # coverage for 414
        with self.assertRaises(ValueError):
            self.cat.import_catalogue(BACKUP_PATH / "nonexistent.zip")

    @patch("zipfile.ZipFile")
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
            zf.writestr("bad_json_dir/" + self.settings.json_filename, "invalid json")

        with self.assertLogs(level="WARNING") as cm:
            self.cat.import_catalogue(zip_path)
        log_out = " ".join(cm.output)
        self.assertIn("does not contain a snapshot json file", log_out)
        self.assertIn("snapshot ID is missing from json", log_out)
        self.assertIn("Failed to import snapshot", log_out)

    @patch("zipfile.ZipFile")
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
            zf.writestr(self.settings.json_filename, "invalid json")

        with self.assertRaises(ValueError):
            self.cat.import_snapshot(zip_path)
