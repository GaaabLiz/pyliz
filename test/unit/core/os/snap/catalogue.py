"""Tests for catalogue discovery, metadata, and manager operations."""

import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from pylizlib.core.data.gen import gen_random_string
from pylizlib.core.os.snap.catalogue import SnapshotCatalogue
from pylizlib.core.os.snap.domain import (
    SnapDirAssociation,
    Snapshot,
)
from pylizlib.core.os.snap.serializer import SnapshotSerializer
from test.support.snapshot import (
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
from test.support.snapshot import (
    make_catalogue as _cat,
)
from test.support.snapshot import (
    make_catalogue_with_backup as _cat_with_backup,
)


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

    def test_get_by_id_reads_only_the_requested_snapshot_metadata(self):

        for snap_id in ("DirectLookupA", "DirectLookupB", "DirectLookupC"):
            self.cat.add(Snapshot(id=snap_id, name=snap_id, desc=""))

        with (
            patch.object(self.cat, "get_all", side_effect=AssertionError("full catalogue scan")),
            patch.object(SnapshotSerializer, "from_json", wraps=SnapshotSerializer.from_json) as read_metadata,
        ):
            result = self.cat.get_by_id("DirectLookupB")

        self.assertIsNotNone(result)
        self.assertEqual(result.id, "DirectLookupB")
        self.assertEqual(read_metadata.call_count, 1)

    def test_add_multiple_snapshots(self):
        for i in range(3):
            self.cat.add(make_snapshot(f"Multi{i}", self._src, n=1))
        self.assertEqual(len(self.cat.get_all()), 3)

    def test_add_rejects_duplicate_id_without_changing_stored_snapshot(self):
        snap = make_snapshot("ExistingSnapshot", self._src, n=1)
        self.cat.add(snap)
        dest = CATALOGUE_PATH / snap.id
        before = {p.relative_to(dest): p.read_bytes() for p in dest.rglob("*") if p.is_file()}
        replacement = snap.clone()
        replacement.name = "Must not replace"
        (self._src[0] / "new.txt").write_text("new source content")

        with self.assertRaises(FileExistsError):
            self.cat.add(replacement)

        self.assertEqual({p.relative_to(dest): p.read_bytes() for p in dest.rglob("*") if p.is_file()}, before)
        self.assertEqual(set(CATALOGUE_PATH.iterdir()), {dest, CATALOGUE_PATH / ".pyliz_snapshot.lock"})

    def test_get_all_skips_corrupted_entries(self):
        # Create a valid snapshot
        snap = make_snapshot("ValidSnap", self._src, n=1)
        self.cat.add(snap)

        # Create a corrupted entry (directory without json)
        corrupted_dir = CATALOGUE_PATH / "corrupted_id"
        corrupted_dir.mkdir()
        (corrupted_dir / "some_file.txt").write_text("x")

        # get_all should skip the corrupted entry and return only the valid one
        all_snaps = self.cat.get_all()
        self.assertEqual(len(all_snaps), 1)
        self.assertEqual(all_snaps[0].id, snap.id)

    def test_get_all_and_export_only_include_published_matching_catalogue_entries(self):

        published = Snapshot(id="abc", name="Published", desc="")
        self.cat.add(published)
        for directory_name in ("_staging_create_abc_test", ".archive_staging_test", "abc_bck_test", "wrong-name"):
            operational_or_mismatched = CATALOGUE_PATH / directory_name
            operational_or_mismatched.mkdir()
            SnapshotSerializer.to_json(published, operational_or_mismatched / "snapshot.json")
            (operational_or_mismatched / "duplicate-payload.txt").write_text(directory_name, encoding="utf-8")

        self.assertEqual([snapshot.id for snapshot in self.cat.get_all()], ["abc"])
        self.assertEqual([snapshot.id for snapshot in self.cat.get_all(strict=True)], ["abc"])

        export_dir = TEST_LOCAL_ROOT / "published_export"
        export_dir.mkdir()
        self.cat.export_catalogue(export_dir, "published-only.zip")
        with zipfile.ZipFile(export_dir / "published-only.zip") as archive:
            entries = archive.namelist()
        self.assertEqual(entries, ["abc/snapshot.json"])

    def test_delete_removes_snapshot(self):
        snap = make_snapshot("DelSnap", self._src, n=1)
        self.cat.add(snap)
        self.cat.delete(snap)
        self.assertFalse(self.cat.exists(snap.id))

    def test_delete_reports_filesystem_failure(self):
        snap = make_snapshot("LockedDelete", self._src, n=1)
        self.cat.add(snap)
        dest = CATALOGUE_PATH / snap.id
        before = {p.relative_to(dest): p.read_bytes() for p in dest.rglob("*") if p.is_file()}

        with patch("pylizlib.core.os.filesystem.directories.shutil.rmtree", side_effect=PermissionError("snapshot is locked")):
            with self.assertRaisesRegex(PermissionError, "snapshot is locked"):
                self.cat.delete(snap)

        self.assertTrue(dest.is_dir())
        self.assertEqual({p.relative_to(dest): p.read_bytes() for p in dest.rglob("*") if p.is_file()}, before)

    def test_get_snap_directory_path_returns_existing_path(self):
        snap = make_snapshot("DirPath", self._src, n=1)
        self.cat.add(snap)
        with patch.object(self.cat, "get_by_id", side_effect=AssertionError("metadata reload")):
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

    def test_failed_backup_blocks_every_protected_operation(self):
        for operation in ("delete", "install", "modify"):
            with self.subTest(operation=operation):
                snap = make_snapshot(f"Protected{operation}", self._src, n=1)
                self.cat.add(snap)
                dest = CATALOGUE_PATH / snap.id
                (self._src[0] / "live_only.txt").write_text("must survive installation")
                before_snapshot = {p.relative_to(dest): p.read_bytes() for p in dest.rglob("*") if p.is_file()}
                before_source = {p.relative_to(SOURCE_DATA_PATH): p.read_bytes() for p in SOURCE_DATA_PATH.rglob("*") if p.is_file()}

                with patch.object(zipfile.ZipFile, "write", side_effect=OSError("backup disk full")):
                    with self.assertRaisesRegex(OSError, "backup disk full"):
                        if operation == "delete":
                            self.cat.delete(snap)
                        elif operation == "install":
                            self.cat.install(snap)
                        else:
                            changed = snap.clone()
                            changed.name = "Must not be saved"
                            changed.directories.clear()
                            self.cat.update_snapshot_by_objs(snap, changed)

                self.assertTrue(dest.is_dir())
                self.assertEqual({p.relative_to(dest): p.read_bytes() for p in dest.rglob("*") if p.is_file()}, before_snapshot)
                self.assertEqual({p.relative_to(SOURCE_DATA_PATH): p.read_bytes() for p in SOURCE_DATA_PATH.rglob("*") if p.is_file()}, before_source)
                self.assertEqual(list(BACKUP_PATH.iterdir()), [])

    def test_delete_creates_backup_when_enabled(self):
        snap = make_snapshot("DelBck", self._src, n=1)
        self.cat.add(snap)
        self.cat.delete(snap)
        backups = list(BACKUP_PATH.glob("backup_beforeDelete_*.zip"))
        self.assertEqual(len(backups), 1)

    def test_install_creates_backup_when_enabled(self):
        snap = make_snapshot("InstBck", self._src, n=1)
        self.cat.add(snap)

        # Populate the original directory with some content so the backup has something to save
        original_dir = Path(snap.directories[0].original_path)
        original_dir.mkdir(parents=True, exist_ok=True)
        (original_dir / "pre_install_file.txt").write_text("content to backup")

        self.cat.install(snap)
        backups = list(BACKUP_PATH.glob("backup_preinstall_*.zip"))
        self.assertEqual(len(backups), 1)

        # Verify the content of the ZIP, not just its existence (P0-02)
        with zipfile.ZipFile(backups[0]) as zf:
            names = zf.namelist()
        self.assertTrue(any("pre_install_file.txt" in n for n in names))

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
        new.directories.append(SnapDirAssociation(index=99, original_path=str(src_sorted[2]), folder_id=gen_random_string(6)))
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
