"""
Integration tests for the complete snapshot system.

These tests exercise multiple modules working together in realistic, end-to-end
scenarios.  They use actual files on disk (text and binary images) and validate
that the entire pipeline — create, install, modify, update, search, backup,
restore, export, import — works correctly.

Scenarios:
    A  Full lifecycle with real images (create → install → modify → update → reinstall)
    B  Multi-snapshot sort, catalogue export, re-import
    C  Duplicate independence (BUG-2 regression with catalogue-level API)
    D  Real images survive snapshot round-trip (byte-for-byte identical)
    E  Search remains usable after source directory removal
    F  Full backup/restore chain (_sd + _ad) preserves data integrity
    G  Large-scale catalogue: 10 snapshots, bulk operations
    H  Concurrent data dict updates reflected in JSON correctly
"""

import shutil
import unittest
from datetime import datetime
from pathlib import Path

from pylizlib.core.data.gen import gen_random_string
from pylizlib.core.os.snap.catalogue import SnapshotCatalogue
from pylizlib.core.os.snap.domain import (
    BackupType,
    SnapDirAssociation,
    Snapshot,
    SnapshotSettings,
)
from pylizlib.core.os.snap.manager import SnapshotManager
from pylizlib.core.os.snap.searcher import (
    SearchTarget,
    SnapshotSearcher,
    SnapshotSearchParams,
)
from pylizlib.core.os.snap.serializer import SnapshotSerializer
from pylizlib.core.os.snap.utils import SnapshotUtils
from pylizlib.core.os.snap.domain import SnapshotSortKey
from test.core.os.snap.conftest import (
    BACKUP_PATH,
    CATALOGUE_PATH,
    SOURCE_DATA_PATH,
    TEST_LOCAL_ROOT,
    downloader,
    make_snapshot,
    reset_index,
    setup_test_dirs,
    teardown_test_dirs,
)


class TestIntegrationScenarioA(unittest.TestCase):
    """Create → install → modify source → update internal → reinstall."""

    def setUp(self):
        setup_test_dirs()
        self.cat = SnapshotCatalogue(CATALOGUE_PATH, settings=SnapshotSettings(backup_path=BACKUP_PATH))

    def tearDown(self):
        teardown_test_dirs()

    def test_full_lifecycle_with_real_images(self):
        src = downloader.create_sample_directory(
            SOURCE_DATA_PATH,
            "scene_a",
            image_count=2,
            extra_text_files={"meta.txt": "version=1"},
        )
        reset_index()
        snap = Snapshot(
            id=gen_random_string(10),
            name="ScenarioA",
            desc="",
            directories=[SnapDirAssociation(index=1, original_path=str(src), folder_id="sca1")],
        )
        self.cat.add(snap)
        self.cat.install(snap)
        self.assertTrue((src / "meta.txt").exists())

        # Modify the source
        (src / "meta.txt").write_text("version=2")
        (src / "extra.jpg").write_bytes(b"\xff\xd8\xff" + b"\x00" * 100)

        # Pull the changes into the internal snapshot copy
        self.cat.update_assoc_with_installed(snap.id)
        snap_dir = self.cat.get_snap_directory_path(snap)
        internal = snap_dir / snap.directories[0].directory_name
        self.assertEqual((internal / "meta.txt").read_text(), "version=2")
        self.assertTrue((internal / "extra.jpg").exists())

        # Reinstall from the updated internal copy
        (src / "meta.txt").unlink()
        self.cat.install(snap)
        self.assertTrue((src / "meta.txt").exists())
        self.assertEqual((src / "meta.txt").read_text(), "version=2")


class TestIntegrationScenarioB(unittest.TestCase):
    """Multiple snapshots: sort, export catalogue, re-import."""

    def setUp(self):
        setup_test_dirs()
        self.cat = SnapshotCatalogue(CATALOGUE_PATH)

    def tearDown(self):
        teardown_test_dirs()

    def test_multi_snap_sort_export_reimport(self):
        dirs = []
        for i, size in enumerate([100, 5_000, 50_000]):
            d = SOURCE_DATA_PATH / f"scb_{i}"
            d.mkdir()
            (d / f"file_{i}.txt").write_text("x" * size)
            dirs.append(d)

        for i, d in enumerate(dirs):
            reset_index()
            s = Snapshot(
                id=gen_random_string(8),
                name=f"ScenB_{i}",
                desc="",
                directories=[SnapDirAssociation(index=1, original_path=str(d), folder_id=f"sb{i}")],
            )
            self.cat.add(s)

        all_snaps = self.cat.get_all()
        sorted_snaps = SnapshotUtils.sort_snapshots(all_snaps, SnapshotSortKey.NAME)
        names = [s.name for s in sorted_snaps]
        self.assertEqual(names, sorted(names, key=str.lower))

        exp_dir = TEST_LOCAL_ROOT / "scb_export"
        exp_dir.mkdir()
        self.cat.export_catalogue(exp_dir, "scb.zip")
        self.assertTrue((exp_dir / "scb.zip").exists())

        for s in self.cat.get_all():
            self.cat.delete(s)
        self.assertEqual(len(self.cat.get_all()), 0)
        self.cat.import_catalogue(exp_dir / "scb.zip")
        self.assertEqual(len(self.cat.get_all()), 3)


class TestIntegrationScenarioC(unittest.TestCase):
    """Duplicate → edit duplicate → verify originals unchanged (BUG-2 regression)."""

    def setUp(self):
        setup_test_dirs()
        self.cat = SnapshotCatalogue(CATALOGUE_PATH)

    def tearDown(self):
        teardown_test_dirs()

    def test_duplicate_independence(self):
        src = SOURCE_DATA_PATH / "scc"
        src.mkdir()
        (src / "data.txt").write_text("original data")
        reset_index()
        original = Snapshot(
            id=gen_random_string(8),
            name="SccOriginal",
            desc="",
            directories=[SnapDirAssociation(index=1, original_path=str(src), folder_id="scc1")],
        )
        self.cat.add(original)
        original_id_before = original.id

        self.cat.duplicate_by_id(original.id)
        # BUG-2 regression
        self.assertEqual(original.id, original_id_before)

        all_snaps = self.cat.get_all()
        copy_snap = next(s for s in all_snaps if s.id != original.id)
        copy_snap.name = "SccCopy_modified"
        SnapshotManager(copy_snap, CATALOGUE_PATH).update_json_base_fields()

        orig_from_cat = self.cat.get_by_id(original.id)
        self.assertEqual(orig_from_cat.name, "SccOriginal")


class TestIntegrationScenarioD(unittest.TestCase):
    """Downloaded images must survive the snapshot add/install cycle byte-for-byte."""

    def setUp(self):
        setup_test_dirs()
        self.cat = SnapshotCatalogue(CATALOGUE_PATH)

    def tearDown(self):
        teardown_test_dirs()

    def test_real_images_survive_snapshot_round_trip(self):
        img_dir = downloader.create_sample_directory(
            SOURCE_DATA_PATH,
            "real_imgs",
            image_count=3,
        )
        reset_index()
        snap = Snapshot(
            id=gen_random_string(8),
            name="RealImages",
            desc="",
            directories=[SnapDirAssociation(index=1, original_path=str(img_dir), folder_id="ri1")],
        )
        self.cat.add(snap)
        snap_dir = self.cat.get_snap_directory_path(snap)
        internal = snap_dir / snap.directories[0].directory_name

        for orig in sorted(img_dir.glob("*.jpg")):
            copy = internal / orig.name
            self.assertTrue(copy.exists(), f"Image {orig.name} not found in snapshot")
            self.assertEqual(orig.read_bytes(), copy.read_bytes(), f"Image {orig.name} content differs")


class TestIntegrationScenarioE(unittest.TestCase):
    """Snapshot internal copy is searchable after source directory removal."""

    def setUp(self):
        setup_test_dirs()
        self.cat = SnapshotCatalogue(CATALOGUE_PATH)

    def tearDown(self):
        teardown_test_dirs()

    def test_search_still_works_after_source_removal(self):
        src = SOURCE_DATA_PATH / "sce"
        src.mkdir()
        (src / "searchable.txt").write_text("find_this_unique_string")

        reset_index()
        snap = Snapshot(
            id=gen_random_string(8),
            name="SceSnap",
            desc="",
            directories=[SnapDirAssociation(index=1, original_path=str(src), folder_id="sce1")],
        )
        self.cat.add(snap)
        searcher = SnapshotSearcher(self.cat)
        params = SnapshotSearchParams(
            query="find_this_unique_string",
            search_target=SearchTarget.FILE_CONTENT,
        )

        results_before = searcher.search(snap, params)
        self.assertGreater(len(results_before), 0)

        shutil.rmtree(src)
        results_after = searcher.search(snap, params)
        self.assertGreater(len(results_after), 0)


class TestIntegrationScenarioF(unittest.TestCase):
    """Full backup/restore chain: _sd backup then _ad backup, both restore correctly."""

    def setUp(self):
        setup_test_dirs()
        settings = SnapshotSettings(backup_path=BACKUP_PATH)
        self.cat = SnapshotCatalogue(CATALOGUE_PATH, settings=settings)

    def tearDown(self):
        teardown_test_dirs()

    def test_sd_backup_restores_full_snapshot_directory(self):
        src = SOURCE_DATA_PATH / "scf_src"
        src.mkdir()
        (src / "important.txt").write_text("critical data")
        reset_index()
        snap = Snapshot(
            id=gen_random_string(8),
            name="ScenF_SD",
            desc="",
            directories=[SnapDirAssociation(index=1, original_path=str(src), folder_id="scf1")],
        )
        self.cat.add(snap)

        mgr = SnapshotManager(snap, CATALOGUE_PATH, SnapshotSettings(backup_path=BACKUP_PATH))
        mgr.create_backup(BACKUP_PATH, "before_delete", BackupType.SNAPSHOT_DIRECTORY)
        backup_zip = sorted(BACKUP_PATH.glob("*_sd_*.zip"))[-1]

        shutil.rmtree(CATALOGUE_PATH / snap.id)
        self.assertFalse((CATALOGUE_PATH / snap.id).exists())

        self.cat.restore_backup(backup_zip)
        self.assertTrue((CATALOGUE_PATH / snap.id).exists())
        restored = self.cat.get_by_id(snap.id)
        self.assertEqual(restored.name, "ScenF_SD")
        snap_dir = self.cat.get_snap_directory_path(restored)
        internal = snap_dir / restored.directories[0].directory_name
        self.assertTrue((internal / "important.txt").exists())

    def test_ad_backup_restores_source_directory_content(self):
        src = SOURCE_DATA_PATH / "scf_ad"
        src.mkdir()
        (src / "config.cfg").write_text("setting=original")
        reset_index()
        snap = Snapshot(
            id=gen_random_string(8),
            name="ScenF_AD",
            desc="",
            directories=[SnapDirAssociation(index=1, original_path=str(src), folder_id="scf2")],
        )
        self.cat.add(snap)

        mgr = SnapshotManager(snap, CATALOGUE_PATH, SnapshotSettings(backup_path=BACKUP_PATH))
        mgr.create_backup(BACKUP_PATH, "before_install", BackupType.ASSOCIATED_DIRECTORIES)
        backup_zip = sorted(BACKUP_PATH.glob("*_ad_*.zip"))[-1]

        (src / "config.cfg").write_text("setting=CORRUPTED")
        self.cat.restore_backup(backup_zip)
        self.assertEqual((src / "config.cfg").read_text(), "setting=original")


class TestIntegrationScenarioG(unittest.TestCase):
    """Large-scale catalogue: 10 snapshots with bulk operations."""

    def setUp(self):
        setup_test_dirs()
        self.cat = SnapshotCatalogue(CATALOGUE_PATH)

    def tearDown(self):
        teardown_test_dirs()

    def test_ten_snapshots_add_list_sort_delete(self):
        added_ids: list[str] = []
        for i in range(10):
            d = SOURCE_DATA_PATH / f"bulk_{i}"
            d.mkdir()
            (d / f"file_{i}.txt").write_text(f"content {i}")
            reset_index()
            snap = Snapshot(
                id=gen_random_string(8),
                name=f"Bulk_{i:02d}",
                desc=f"Bulk snapshot {i}",
                directories=[SnapDirAssociation(index=1, original_path=str(d), folder_id=f"b{i}")],
            )
            self.cat.add(snap)
            added_ids.append(snap.id)

        all_snaps = self.cat.get_all()
        self.assertEqual(len(all_snaps), 10)

        sorted_snaps = SnapshotUtils.sort_snapshots(all_snaps, SnapshotSortKey.NAME)
        names = [s.name for s in sorted_snaps]
        self.assertEqual(names, sorted(names, key=str.lower))

        # Delete half and verify count
        for snap_id in added_ids[:5]:
            snap = self.cat.get_by_id(snap_id)
            self.cat.delete(snap)
        self.assertEqual(len(self.cat.get_all()), 5)


class TestIntegrationScenarioH(unittest.TestCase):
    """Data dictionary updates reflected correctly in JSON."""

    def setUp(self):
        setup_test_dirs()
        self.cat = SnapshotCatalogue(CATALOGUE_PATH)

    def tearDown(self):
        teardown_test_dirs()

    def test_data_dict_updates_persist_across_reloads(self):
        src = SOURCE_DATA_PATH / "sch"
        src.mkdir()
        (src / "f.txt").write_text("data")
        reset_index()
        snap = Snapshot(
            id=gen_random_string(8),
            name="ScenH",
            desc="",
            directories=[SnapDirAssociation(index=1, original_path=str(src), folder_id="sch1")],
        )
        self.cat.add(snap)

        snap.add_data_item("env", "staging")
        snap.add_data_item("version", "2.0.0")
        mgr = SnapshotManager(snap, CATALOGUE_PATH, SnapshotSettings())
        mgr.update_json_data_fields()

        reloaded = self.cat.get_by_id(snap.id)
        self.assertEqual(reloaded.data.get("env"), "staging")
        self.assertEqual(reloaded.data.get("version"), "2.0.0")
        self.assertIsNotNone(reloaded.date_last_modified)


class TestBugFixesRegression(unittest.TestCase):
    """Explicit regression tests for all three known bugs."""

    def setUp(self):
        setup_test_dirs()

    def tearDown(self):
        teardown_test_dirs()

    def test_bug1_snapshot_date_created_unique_per_instance(self):
        """BUG-1: date_created must not be a shared default."""
        import time
        first = Snapshot(id="x", name="x", desc="")
        time.sleep(0.02)
        second = Snapshot(id="y", name="y", desc="")
        self.assertLessEqual(first.date_created, second.date_created)
        self.assertIsNot(first.date_created, second.date_created)

    def test_bug2_duplicate_preserves_original_snapshot_in_full_pipeline(self):
        """BUG-2: SnapshotManager.duplicate() must not mutate self.snapshot."""
        src = SOURCE_DATA_PATH / "bug2"
        src.mkdir()
        (src / "f.txt").write_text("original")
        reset_index()
        snap = Snapshot(
            id=gen_random_string(8),
            name="BugOriginal",
            desc="",
            directories=[SnapDirAssociation(index=1, original_path=str(src), folder_id="b2")],
        )
        mgr = SnapshotManager(snap, CATALOGUE_PATH, SnapshotSettings())
        mgr.create()
        original_id = snap.id
        original_name = snap.name
        mgr.duplicate()
        self.assertEqual(snap.id, original_id)
        self.assertEqual(snap.name, original_name)
        orig_json = SnapshotSerializer.from_json(mgr.path_snapshot_json)
        self.assertEqual(orig_json.id, original_id)

    def test_bug3_date_last_used_survives_json_round_trip(self):
        """BUG-3: date_last_used must be handled correctly in from_json."""
        src = SOURCE_DATA_PATH / "bug3"
        src.mkdir()
        (src / "f.txt").write_text("data")
        reset_index()
        snap = Snapshot(
            id=gen_random_string(8),
            name="Bug3",
            desc="",
            directories=[SnapDirAssociation(index=1, original_path=str(src), folder_id="b3")],
        )
        expected = datetime(2025, 12, 25, 10, 30, 0)
        snap.date_last_used = expected

        json_path = TEST_LOCAL_ROOT / "bug3.json"
        SnapshotSerializer.to_json(snap, json_path)
        loaded = SnapshotSerializer.from_json(json_path)

        self.assertIsNotNone(loaded.date_last_used)
        self.assertEqual(loaded.date_last_used, expected)


if __name__ == "__main__":
    unittest.main()
