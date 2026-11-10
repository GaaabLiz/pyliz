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

import errno
import os
import shutil
import types
import unittest
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from pylizlib.core.data.gen import gen_random_string
from pylizlib.core.log.pylizLogger import logger
from pylizlib.core.os.snap.catalogue import SnapshotCatalogue
from pylizlib.core.os.snap.copy_strategy import SequentialFileCopyStrategy
from pylizlib.core.os.snap.domain import (
    BackupType,
    SnapDirAssociation,
    SnapEditType,
    Snapshot,
    SnapshotSettings,
)
from pylizlib.core.os.snap.integrity import SnapshotIntegrityError
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
            self.assertIsNotNone(assoc.integrity_manifest)
            self.assertIn(".", assoc.integrity_manifest)

    def test_create_uses_strategy_from_snapshot_settings(self):
        class RecordingStrategy(SequentialFileCopyStrategy):
            def __init__(self):
                self.sources = []

            def copy_directory(
                self,
                source,
                destination,
                progress_callback=None,
                message_callback=None,
                *,
                manifest=None,
                expected_manifest=None,
            ):
                self.sources.append(Path(source))
                return super().copy_directory(
                    source,
                    destination,
                    progress_callback,
                    message_callback,
                    manifest=manifest,
                    expected_manifest=expected_manifest,
                )

        snap = make_snapshot("ConfiguredCopyStrategy", self._src, n=2)
        strategy = RecordingStrategy()
        mgr = self._mgr(snap, SnapshotSettings(copy_strategy=strategy))

        mgr.create()

        self.assertEqual(strategy.sources, [Path(assoc.original_path) for assoc in snap.directories])

    def test_create_explicitly_replaces_existing_contents(self):
        snap = make_snapshot("MgrRecreate", self._src, n=1)
        mgr = self._mgr(snap)
        mgr.create()
        leftover = mgr.path_snapshot / "leftover.txt"
        leftover.write_text("stale")
        (self._src[0] / "new.txt").write_text("new version")
        snap.name = "Explicit replacement"
        mgr.create(replace_existing=True)
        self.assertFalse(leftover.exists())
        self.assertEqual((mgr.path_snapshot / snap.directories[0].directory_name / "new.txt").read_text(), "new version")
        self.assertEqual(SnapshotSerializer.from_json(mgr.path_snapshot_json).name, "Explicit replacement")
        self.assertEqual(list(CATALOGUE_PATH.iterdir()), [mgr.path_snapshot])

    def test_create_rejects_existing_snapshot_by_default(self):
        snap = make_snapshot("CreateConflict", self._src, n=1)
        mgr = self._mgr(snap)
        mgr.create()
        before = {p.relative_to(mgr.path_snapshot): p.read_bytes() for p in mgr.path_snapshot.rglob("*") if p.is_file()}
        (self._src[0] / "new.txt").write_text("new version")

        with self.assertRaises(FileExistsError):
            mgr.create()

        self.assertEqual({p.relative_to(mgr.path_snapshot): p.read_bytes() for p in mgr.path_snapshot.rglob("*") if p.is_file()}, before)
        self.assertEqual(list(CATALOGUE_PATH.iterdir()), [mgr.path_snapshot])

    def test_create_preserves_existing_snapshot_when_publication_fails(self):
        snap = make_snapshot("RecreatePublishFail", self._src, n=1)
        mgr = self._mgr(snap)
        mgr.create()
        (mgr.path_snapshot / "original_only.txt").write_text("must survive")
        before = {p.relative_to(mgr.path_snapshot): p.read_bytes() for p in mgr.path_snapshot.rglob("*") if p.is_file()}
        (self._src[0] / "new.txt").write_text("new version")
        real_rename = Path.rename
        failed = False

        def fail_publication(source, target):
            nonlocal failed
            if not failed and Path(target) == mgr.path_snapshot:
                failed = True
                raise PermissionError("final rename denied")
            return real_rename(source, target)

        with patch.object(Path, "rename", autospec=True, side_effect=fail_publication):
            with self.assertRaisesRegex(PermissionError, "final rename denied"):
                mgr.create(replace_existing=True)

        self.assertTrue(failed)
        self.assertTrue(mgr.path_snapshot.is_dir())
        self.assertEqual({p.relative_to(mgr.path_snapshot): p.read_bytes() for p in mgr.path_snapshot.rglob("*") if p.is_file()}, before)
        self.assertEqual(list(CATALOGUE_PATH.iterdir()), [mgr.path_snapshot])

    def test_create_preserves_existing_snapshot_when_backup_rename_fails(self):
        snap = make_snapshot("RecreateBackupFail", self._src, n=1)
        mgr = self._mgr(snap)
        mgr.create()
        before = {p.relative_to(mgr.path_snapshot): p.read_bytes() for p in mgr.path_snapshot.rglob("*") if p.is_file()}

        with patch.object(Path, "rename", side_effect=PermissionError("backup rename denied")):
            with self.assertRaisesRegex(PermissionError, "backup rename denied"):
                mgr.create(replace_existing=True)

        self.assertEqual({p.relative_to(mgr.path_snapshot): p.read_bytes() for p in mgr.path_snapshot.rglob("*") if p.is_file()}, before)
        self.assertEqual(list(CATALOGUE_PATH.iterdir()), [mgr.path_snapshot])

    def test_create_preserves_recovery_copies_when_rollback_also_fails(self):
        snap = make_snapshot("RecreateRollbackFail", self._src, n=1)
        mgr = self._mgr(snap)
        mgr.create()
        (mgr.path_snapshot / "original_only.txt").write_text("must survive")
        before = {p.relative_to(mgr.path_snapshot): p.read_bytes() for p in mgr.path_snapshot.rglob("*") if p.is_file()}
        (self._src[0] / "new.txt").write_text("new version")
        real_rename = Path.rename

        def fail_publication_and_rollback(source, target):
            if Path(target) == mgr.path_snapshot:
                raise PermissionError("destination unavailable")
            return real_rename(source, target)

        with patch.object(Path, "rename", autospec=True, side_effect=fail_publication_and_rollback):
            with self.assertRaises(PermissionError):
                mgr.create(replace_existing=True)

        transaction = next(CATALOGUE_PATH.glob(f"_staging_create_{snap.id}_*"))
        original = transaction / "original"
        prepared = transaction / "new"
        self.assertEqual({p.relative_to(original): p.read_bytes() for p in original.rglob("*") if p.is_file()}, before)
        self.assertEqual((prepared / snap.directories[0].directory_name / "new.txt").read_text(), "new version")
        self.assertEqual(SnapshotSerializer.from_json(prepared / "snapshot.json").id, snap.id)

    def test_create_keeps_replacement_when_backup_cleanup_partially_fails(self):
        snap = make_snapshot("RecreateCleanupFail", self._src, n=1)
        mgr = self._mgr(snap)
        mgr.create()
        (self._src[0] / "new.txt").write_text("new version")
        real_rmtree = shutil.rmtree
        damaged_backups = []

        def fail_cleanup(path, *args, **kwargs):
            backup = Path(path) / "original"
            if backup.is_dir():
                next(p for p in backup.rglob("*") if p.is_file()).unlink()
                damaged_backups.append(backup)
                raise PermissionError("cleanup interrupted")
            return real_rmtree(path, *args, **kwargs)

        with patch("shutil.rmtree", side_effect=fail_cleanup):
            with self.assertLogs("PylizLib", level="WARNING") as logs:
                mgr.create(replace_existing=True)

        self.assertEqual(len(damaged_backups), 1)
        self.assertIn(str(damaged_backups[0].parent), " ".join(logs.output))
        self.assertEqual((mgr.path_snapshot / snap.directories[0].directory_name / "new.txt").read_text(), "new version")
        self.assertEqual((mgr.path_snapshot / snap.directories[0].directory_name / "m1_file.txt").read_text(), "content of m1")
        self.assertEqual(SnapshotSerializer.from_json(mgr.path_snapshot_json).id, snap.id)


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

    @patch("pylizlib.core.os.snap.domain.SnapDirAssociation.copy_install_to")
    def test_create_rollback_on_failure(self, mock_copy):
        snap = make_snapshot("CreateFail", self._src, n=1)
        mgr = self._mgr(snap)
        mock_copy.side_effect = Exception("simulated copy error")

        with self.assertRaises(Exception):
            mgr.create()

        # Ensure that no partial directory or staging directory is left behind
        staging_dirs = list(mgr.path_catalogue.glob(f"_staging_create_{snap.id}_*"))
        self.assertEqual(len(staging_dirs), 0)
        self.assertFalse(mgr.path_snapshot.exists())


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

    def test_failed_directory_removal_keeps_association_and_metadata(self):
        snap = make_snapshot("LockedAssociation", self._src, n=1)
        mgr = self._mgr(snap)
        mgr.create()
        assoc = snap.directories[0]
        before = mgr.path_snapshot_json.read_bytes()

        with patch("os.unlink", side_effect=PermissionError("association is locked")):
            with self.assertRaisesRegex(PermissionError, "association is locked"):
                mgr.uninstall_directory_by_folder_id(assoc.folder_id)

        self.assertEqual(snap.directories, [assoc])
        self.assertEqual(mgr.path_snapshot_json.read_bytes(), before)
        self.assertTrue((mgr.path_snapshot / assoc.directory_name / "dm1_file.txt").is_file())

    def test_remove_installed_copies_reports_failures_after_attempting_other_targets(self):
        snap = make_snapshot("BulkRemovalFailure", self._src, n=2)
        mgr = self._mgr(snap)
        mgr.create()
        before = mgr.path_snapshot_json.read_bytes()
        real_unlink = os.unlink

        def fail_first_target(path, *args, **kwargs):
            if Path(path).name == "dm1_file.txt":
                raise PermissionError("first target is locked")
            return real_unlink(path, *args, **kwargs)

        with patch("os.unlink", side_effect=fail_first_target):
            with self.assertRaises(ExceptionGroup) as ctx:
                mgr.remove_installed_copies()

        self.assertEqual(len(ctx.exception.exceptions), 1)
        self.assertIsInstance(ctx.exception.exceptions[0], PermissionError)
        self.assertTrue((self._src[0] / "dm1_file.txt").is_file())
        self.assertFalse(self._src[1].exists())
        self.assertEqual(mgr.path_snapshot_json.read_bytes(), before)


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
        self.assertIn("new_file.txt", loaded.directories[0].integrity_manifest)

    def test_missing_source_aborts_update(self):
        snap = make_snapshot("AssocMissing", self._src, n=1)
        mgr = self._mgr(snap)
        mgr.create()
        original_dir = Path(snap.directories[0].original_path)
        shutil.rmtree(original_dir)

        with self.assertRaises(FileNotFoundError) as ctx:
            mgr.update_associated_dirs_from_system()
        self.assertIn("does not exist", str(ctx.exception))

        # Verify the original snapshot backup still exists (no data loss)
        snapshot_copy_path = mgr.path_snapshot / snap.directories[0].directory_name
        self.assertTrue(snapshot_copy_path.exists())
        self.assertTrue((snapshot_copy_path / "ua1_file.txt").exists())


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
        mgr.install(clear_destination=True)
        self.assertFalse((original_dir / "extra.txt").exists())
        self.assertTrue((original_dir / "i1_file.txt").exists())
        loaded = SnapshotSerializer.from_json(mgr.path_snapshot_json)
        self.assertIsNotNone(loaded.date_last_used)

    def test_install_merges_content_when_clear_destination_false(self):
        snap = make_snapshot("MgrInstallMerge", self._src, n=1)
        mgr = self._mgr(snap)
        mgr.create()
        original_dir = Path(snap.directories[0].original_path)
        (original_dir / "extra.txt").write_text("should be kept")
        mgr.install(clear_destination=False)
        # extra.txt should still exist because we didn't clear
        self.assertTrue((original_dir / "extra.txt").exists())
        self.assertTrue((original_dir / "i1_file.txt").exists())

    def test_install_rolls_back_if_staging_fails(self):
        snap = make_snapshot("MgrInstallFail", self._src, n=1)
        mgr = self._mgr(snap)
        mgr.create()
        original_dir = Path(snap.directories[0].original_path)
        (original_dir / "important_file.txt").write_text("dont lose me")

        # The configured directory-copy strategy must fail before installation.
        with patch.object(mgr.settings.copy_strategy, "copy_directory", side_effect=Exception("Simulated copy failure")):
            with self.assertRaises(RuntimeError):
                mgr.install(clear_destination=True)

        # The installation failed, so the original directory must remain untouched
        self.assertTrue((original_dir / "important_file.txt").exists())
        self.assertEqual((original_dir / "important_file.txt").read_text(), "dont lose me")
        # Ensure no staging or backup dirs leaked
        for item in original_dir.parent.iterdir():
            self.assertFalse("_staging_" in item.name)
            self.assertFalse("_bck_" in item.name)

    def test_install_creates_missing_destinations(self):
        snap = make_snapshot("MgrInstallMiss", self._src, n=1)
        mgr = self._mgr(snap)
        mgr.create()
        original_dir = Path(snap.directories[0].original_path)
        shutil.rmtree(original_dir)  # Make it disappear before install

        mgr.install(clear_destination=True)
        self.assertTrue(original_dir.exists())
        self.assertTrue((original_dir / "i1_file.txt").exists())

    def test_install_fails_preflight_if_source_missing(self):
        snap = make_snapshot("InstPreflight", self._src, n=1)
        mgr = self._mgr(snap)
        mgr.create()
        source_dir = mgr.path_snapshot / snap.directories[0].directory_name
        shutil.rmtree(source_dir)  # Make source disappear

        with self.assertRaises(FileNotFoundError) as ctx:
            mgr.install(clear_destination=True)
        self.assertIn("does not exist inside the snapshot", str(ctx.exception))

    def test_install_rejects_missing_snapshot_file_without_replacing_destination(self):
        snap = make_snapshot("InstallCorrupt", self._src, n=1)
        mgr = self._mgr(snap)
        mgr.create()
        original_dir = Path(snap.directories[0].original_path)
        internal_copy = mgr.path_snapshot / snap.directories[0].directory_name
        (internal_copy / "i1_file.txt").unlink()
        (original_dir / "preserve.txt").write_text("existing destination", encoding="utf-8")

        with self.assertRaisesRegex(SnapshotIntegrityError, "integrity manifest"):
            mgr.install(clear_destination=True)

        self.assertEqual((original_dir / "preserve.txt").read_text(encoding="utf-8"), "existing destination")
        self.assertTrue(original_dir.exists())
        self.assertFalse(list(original_dir.parent.glob("*_staging_*")))

    def test_install_refuses_legacy_snapshot_without_manifest_by_default(self):
        snap = make_snapshot("InstallLegacy", self._src, n=1)
        mgr = self._mgr(snap)
        mgr.create()
        snap.directories[0].integrity_manifest = None
        SnapshotSerializer.to_json(snap, mgr.path_snapshot_json)
        legacy_snapshot = SnapshotSerializer.from_json(mgr.path_snapshot_json)
        legacy_manager = self._mgr(legacy_snapshot)
        original_dir = Path(snap.directories[0].original_path)
        (original_dir / "preserve.txt").write_text("existing destination", encoding="utf-8")

        with self.assertRaisesRegex(SnapshotIntegrityError, "no integrity manifest"):
            legacy_manager.install(clear_destination=True)

        self.assertEqual((original_dir / "preserve.txt").read_text(encoding="utf-8"), "existing destination")

    def test_install_can_explicitly_allow_legacy_snapshot_without_manifest(self):
        snap = make_snapshot("InstallLegacyOptIn", self._src, n=1)
        mgr = self._mgr(snap)
        mgr.create()
        snap.directories[0].integrity_manifest = None
        SnapshotSerializer.to_json(snap, mgr.path_snapshot_json)
        legacy_snapshot = SnapshotSerializer.from_json(mgr.path_snapshot_json)
        settings = SnapshotSettings(allow_unverified_legacy_snapshots=True)
        legacy_manager = SnapshotManager(legacy_snapshot, CATALOGUE_PATH, settings)

        legacy_manager.install(clear_destination=True)

        original_dir = Path(snap.directories[0].original_path)
        self.assertTrue((original_dir / "i1_file.txt").exists())

    def test_remove_installed_copies_deletes_original_paths(self):
        install_dir = TEST_LOCAL_ROOT / "installed_copy"
        install_dir.mkdir(parents=True, exist_ok=True)
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

    def test_remove_installed_copies_blocks_critical_paths(self):
        snap = Snapshot(
            id=gen_random_string(8),
            name="RemCriticalSnap",
            desc="",
            directories=[SnapDirAssociation(index=1, original_path="/usr/bin/test", folder_id="remcrit")],
        )
        mgr = SnapshotManager(snap, CATALOGUE_PATH, SnapshotSettings())
        with self.assertRaises(ValueError) as ctx:
            mgr.remove_installed_copies()
        self.assertIn("critical system path", str(ctx.exception))

    def test_install_blocks_critical_paths(self):
        snap = Snapshot(
            id=gen_random_string(8),
            name="InstCriticalSnap",
            desc="",
            directories=[SnapDirAssociation(index=1, original_path="/usr/bin", folder_id="inscrit")],
        )
        mgr = SnapshotManager(snap, CATALOGUE_PATH, SnapshotSettings())
        source_dir = mgr.path_snapshot / snap.directories[0].directory_name
        source_dir.mkdir(parents=True, exist_ok=True)
        with self.assertRaises(ValueError) as ctx:
            mgr.install()
        self.assertIn("critical system path", str(ctx.exception))


class TestSnapshotManagerActionsAndBackup(unittest.TestCase):
    def setUp(self):
        setup_test_dirs()
        self._src = create_source_dirs(SOURCE_DATA_PATH, ["ab1", "ab2", "ab3"])

    def tearDown(self):
        teardown_test_dirs()

    def _mgr(self, snap, settings=None):
        return SnapshotManager(snap, CATALOGUE_PATH, settings or SnapshotSettings())

    def _create_same_name_snapshot(self, count=2):
        sources = [SOURCE_DATA_PATH / f"source_{i}" / "foo" for i in range(count)]
        for i, source in enumerate(sources):
            source.mkdir(parents=True)
            (source / "foo_file.txt").write_text(f"saved copy {i}")
        snap = make_snapshot("SameNames", sources, n=count)
        self._mgr(snap).create()
        # Updates must preserve the stored copies even if the live sources change.
        for source in sources:
            (source / "foo_file.txt").write_text("changed live source")
        return snap

    def test_remove_and_renumber_same_name_preserves_kept_copy(self):
        snap = self._create_same_name_snapshot()
        new = snap.clone()
        new.directories.pop(0)
        new.directories[0].index = 1
        mgr = self._mgr(new)

        edits = SnapshotUtils.get_edits_between_snapshots(snap, new)
        mgr.update_from_actions_list(edits)

        self.assertEqual((mgr.path_snapshot / "1-foo" / "foo_file.txt").read_text(), "saved copy 1")
        self.assertEqual({p.name for p in mgr.path_snapshot.iterdir()}, {"1-foo", "snapshot.json"})
        self.assertEqual(SnapshotSerializer.from_json(mgr.path_snapshot_json).directories, new.directories)

    def test_reordering_same_name_directories_preserves_each_copy(self):
        snap = self._create_same_name_snapshot(count=3)
        new = snap.clone()
        for assoc, index in zip(new.directories, (2, 3, 1)):
            assoc.index = index
        mgr = self._mgr(new)

        # A plan must work independently of the ordering of its actions.
        edits = SnapshotUtils.get_edits_between_snapshots(snap, new)
        mgr.update_from_actions_list(list(reversed(edits)))

        for i, assoc in enumerate(new.directories):
            self.assertEqual((mgr.path_snapshot / assoc.directory_name / "foo_file.txt").read_text(), f"saved copy {i}")
        self.assertEqual({p.name for p in mgr.path_snapshot.iterdir()}, {"1-foo", "2-foo", "3-foo", "snapshot.json"})

    def test_duplicate_final_names_rejected_before_modifying_snapshot(self):
        snap = self._create_same_name_snapshot()
        new = snap.clone()
        new.directories[1].index = 1
        mgr = self._mgr(snap)
        before = {p.relative_to(mgr.path_snapshot): p.read_bytes() for p in mgr.path_snapshot.rglob("*") if p.is_file()}

        with self.assertRaises(ValueError):
            self._mgr(new)

        self.assertEqual({p.relative_to(mgr.path_snapshot): p.read_bytes() for p in mgr.path_snapshot.rglob("*") if p.is_file()}, before)

    def test_remove_and_renumber_rolls_back_when_final_rename_fails(self):
        snap = self._create_same_name_snapshot()
        new = snap.clone()
        new.directories.pop(0)
        new.directories[0].index = 1
        mgr = self._mgr(new)
        before = {p.relative_to(mgr.path_snapshot): p.read_bytes() for p in mgr.path_snapshot.rglob("*") if p.is_file()}
        real_rename = Path.rename
        failed = False

        def fail_final_rename(source, target):
            nonlocal failed
            if not failed and Path(target) == mgr.path_snapshot / "1-foo" and source.parent != mgr.path_snapshot:
                failed = True
                raise PermissionError("final rename failed")
            return real_rename(source, target)

        with patch.object(Path, "rename", autospec=True, side_effect=fail_final_rename):
            with self.assertRaises(PermissionError):
                mgr.update_from_actions_list(SnapshotUtils.get_edits_between_snapshots(snap, new))

        self.assertEqual({p.relative_to(mgr.path_snapshot): p.read_bytes() for p in mgr.path_snapshot.rglob("*") if p.is_file()}, before)

    def test_reorder_rolls_back_after_one_final_rename_succeeds(self):
        snap = self._create_same_name_snapshot(count=3)
        new = snap.clone()
        for assoc, index in zip(new.directories, (2, 3, 1)):
            assoc.index = index
        mgr = self._mgr(new)
        before = {p.relative_to(mgr.path_snapshot): p.read_bytes() for p in mgr.path_snapshot.rglob("*") if p.is_file()}
        real_rename = Path.rename
        failed = False

        def fail_second_publication(source, target):
            nonlocal failed
            if not failed and Path(target) == mgr.path_snapshot / "3-foo" and source.parent != mgr.path_snapshot:
                failed = True
                raise PermissionError("second final rename failed")
            return real_rename(source, target)

        with patch.object(Path, "rename", autospec=True, side_effect=fail_second_publication):
            with self.assertRaises(PermissionError):
                mgr.update_from_actions_list(SnapshotUtils.get_edits_between_snapshots(snap, new))

        self.assertTrue(failed)
        self.assertEqual({p.relative_to(mgr.path_snapshot): p.read_bytes() for p in mgr.path_snapshot.rglob("*") if p.is_file()}, before)

    def test_update_from_actions_list_applies_add_and_remove(self):
        src_sorted = sorted(self._src)
        snap = make_snapshot("ActionsSnap", src_sorted, n=2)
        mgr = self._mgr(snap)
        mgr.create()

        snap_new = snap.clone()
        removed_assoc = snap_new.directories.pop(0)
        # B is now at index 0 in the list, but its obj still says index 1.
        # Let's fix its index to 0, which simulates UI reordering
        kept_assoc = snap_new.directories[0]
        old_kept_dir_name = kept_assoc.directory_name
        kept_assoc.index = 0
        new_kept_dir_name = kept_assoc.directory_name

        # Add a new one
        snap_new.directories.append(SnapDirAssociation(index=1, original_path=str(src_sorted[2]), folder_id="added999"))

        edits = SnapshotUtils.get_edits_between_snapshots(snap, snap_new)
        # edits should contain a REMOVE, an ADD, and a RENAME (because kept_assoc index changed)
        self.assertEqual(len(edits), 3)
        self.assertTrue(any(e.action_type == SnapEditType.RENAME_DIR for e in edits))

        mgr2 = SnapshotManager(snap_new, CATALOGUE_PATH)
        mgr2.update_from_actions_list(edits)

        self.assertFalse((mgr.path_snapshot / removed_assoc.directory_name).exists())
        self.assertTrue((mgr.path_snapshot / snap_new.directories[-1].directory_name).exists())
        # The kept directory should have been renamed on disk to match its new index
        self.assertFalse((mgr.path_snapshot / old_kept_dir_name).exists())
        self.assertTrue((mgr.path_snapshot / new_kept_dir_name).exists())

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

    def test_failed_backup_preserves_existing_archive_and_removes_partial_file(self):
        snap = make_snapshot("AtomicBackup", self._src, n=1)
        mgr = self._mgr(snap)
        mgr.create()
        real_write = zipfile.ZipFile.write

        def fail_after_write(archive, *args, **kwargs):
            real_write(archive, *args, **kwargs)
            raise OSError("backup write interrupted")

        with patch("pylizlib.core.os.snap.manager.datetime") as mock_datetime:
            mock_datetime.now.return_value.strftime.return_value = "20261105_120000"
            mgr.create_backup(BACKUP_PATH, "atomic", BackupType.SNAPSHOT_DIRECTORY)
            published = next(BACKUP_PATH.glob("*.zip"))
            original_bytes = published.read_bytes()

            with patch.object(zipfile.ZipFile, "write", autospec=True, side_effect=fail_after_write):
                with self.assertRaisesRegex(OSError, "backup write interrupted"):
                    mgr.create_backup(BACKUP_PATH, "atomic", BackupType.SNAPSHOT_DIRECTORY)

        self.assertEqual(published.read_bytes(), original_bytes)
        self.assertEqual(list(BACKUP_PATH.iterdir()), [published])

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

        with patch.object(Path, "replace", side_effect=PermissionError("backup publication denied")):
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


class TestSnapshotManagerWindowsPermissions(unittest.TestCase):
    def setUp(self):
        setup_test_dirs()
        self.sources = create_source_dirs(SOURCE_DATA_PATH, ["permissions"])
        self.snap = make_snapshot("WindowsPermissions", self.sources, n=1)
        self.mgr = SnapshotManager(self.snap, CATALOGUE_PATH)
        self.mgr.create()

    def tearDown(self):
        teardown_test_dirs()

    def _windows_modules(self):
        security = types.ModuleType("win32security")
        constants = types.ModuleType("ntsecuritycon")
        security.LookupAccountName = MagicMock(return_value=("everyone_sid", "domain", 1))
        security.GetFileSecurity = MagicMock()
        security.SetFileSecurity = MagicMock()
        security.DACL_SECURITY_INFORMATION = 1
        security.ACL_REVISION = 2
        constants.OBJECT_INHERIT_ACE = 1
        constants.CONTAINER_INHERIT_ACE = 2
        constants.GENERIC_ALL = 3
        return {"win32security": security, "ntsecuritycon": constants}

    @patch("sys.platform", "win32")
    def test_disabled_or_default_permissions_skip_the_entire_windows_branch(self):
        for mode in ("direct_default", "direct_false", "catalogue_default", "catalogue_false"):
            with self.subTest(mode=mode):
                modules = self._windows_modules()
                imported = []
                real_import = __import__

                def record_import(name, *args, **kwargs):
                    if name in modules:
                        imported.append(name)
                    return real_import(name, *args, **kwargs)

                with patch.dict("sys.modules", modules), patch("builtins.__import__", side_effect=record_import):
                    if mode == "direct_default":
                        self.mgr.install()
                    elif mode == "direct_false":
                        self.mgr.install(enable_everyone_full_control=False)
                    else:
                        settings = SnapshotSettings() if mode == "catalogue_default" else SnapshotSettings(install_with_everyone_full_control=False)
                        SnapshotCatalogue(CATALOGUE_PATH, settings).install(self.snap)

                self.assertEqual(imported, [])
                modules["win32security"].LookupAccountName.assert_not_called()
                modules["win32security"].GetFileSecurity.assert_not_called()
                modules["win32security"].SetFileSecurity.assert_not_called()
                self.assertEqual((self.sources[0] / "permissions_file.txt").read_text(), "content of permissions")

    @patch("sys.platform", "win32")
    def test_catalogue_can_explicitly_enable_everyone_permissions(self):
        modules = self._windows_modules()
        settings = SnapshotSettings(install_with_everyone_full_control=True)

        with patch.dict("sys.modules", modules):
            SnapshotCatalogue(CATALOGUE_PATH, settings).install(self.snap)

        modules["win32security"].SetFileSecurity.assert_called_once()
        dacl = modules["win32security"].GetFileSecurity.return_value.GetSecurityDescriptorDacl.return_value
        dacl.AddAccessAllowedAceEx.assert_called_once_with(2, 3, 3, "everyone_sid")


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
        self.assertTrue(any("does not exist" in out for out in cm.output))

        # Test 229-230
        install_path.mkdir(parents=True, exist_ok=True)
        with patch("shutil.rmtree", side_effect=Exception("mocked error")):
            with self.assertLogs(level="ERROR") as cm2:
                with self.assertRaises(ExceptionGroup):
                    mgr.remove_installed_copies()
            self.assertTrue(any("Failed to remove directory" in out for out in cm2.output))

    @patch("sys.platform", "win32")
    def test_install_win32_no_pywin32(self):
        # coverage 247-252
        snap = make_snapshot("Win32NoPywin32", self._src, n=1)
        mgr = SnapshotManager(snap, CATALOGUE_PATH, SnapshotSettings())
        mgr.create()
        with patch.dict("sys.modules", {"ntsecuritycon": None, "win32security": None}):
            with self.assertLogs(level="ERROR") as cm:
                mgr.install(enable_everyone_full_control=True)
            self.assertTrue(any("pywin32 not installed" in out for out in cm.output))

    @patch("sys.platform", "win32")
    def test_install_win32_with_pywin32_success(self):
        # coverage 295-306
        snap = make_snapshot("Win32Pywin32Succ", self._src, n=1)
        mgr = SnapshotManager(snap, CATALOGUE_PATH, SnapshotSettings())
        mgr.create()
        import types

        mock_win32security = types.ModuleType("win32security")
        mock_ntsecuritycon = types.ModuleType("ntsecuritycon")

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

        with patch.dict("sys.modules", {"ntsecuritycon": mock_ntsecuritycon, "win32security": mock_win32security}):
            mgr.install(enable_everyone_full_control=True)
            mock_win32security.LookupAccountName.assert_called()
            mock_win32security.GetFileSecurity.assert_called()
            mock_dacl.AddAccessAllowedAceEx.assert_called()
            mock_sd.SetSecurityDescriptorDacl.assert_called()
            mock_win32security.SetFileSecurity.assert_called()

    @patch("sys.platform", "win32")
    def test_install_win32_with_pywin32_exceptions(self):
        # coverage 290-313
        snap = make_snapshot("Win32Pywin32", self._src, n=1)
        mgr = SnapshotManager(snap, CATALOGUE_PATH, SnapshotSettings())
        mgr.create()
        import types

        mock_win32security = types.ModuleType("win32security")
        mock_ntsecuritycon = types.ModuleType("ntsecuritycon")

        mock_win32security.LookupAccountName = MagicMock(side_effect=Exception("win32 error"))

        with patch.dict("sys.modules", {"ntsecuritycon": mock_ntsecuritycon, "win32security": mock_win32security}):
            with self.assertLogs(level="ERROR") as cm:
                mgr.install(enable_everyone_full_control=True)
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

        with patch("shutil.copytree", side_effect=Exception("copytree err")):
            with self.assertRaises(RuntimeError) as cm:
                mgr.install()
            self.assertIn("Failed to copy", str(cm.exception))

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


if __name__ == "__main__":
    unittest.main()
