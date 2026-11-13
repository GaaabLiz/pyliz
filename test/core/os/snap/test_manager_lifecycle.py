"""Tests for snapshot creation, duplication, deletion, and metadata updates."""

import os
import shutil
import stat
from pathlib import Path
from unittest.mock import patch

from pylizlib.core.os.snap.copy_strategy import CopyMetadataMode, SequentialFileCopyStrategy
from pylizlib.core.os.snap.domain import (
    SnapDirAssociation,
    Snapshot,
    SnapshotSettings,
)
from pylizlib.core.os.snap.serializer import SnapshotSerializer
from test.core.os.snap.conftest import (
    CATALOGUE_PATH,
    SOURCE_DATA_PATH,
    TEST_LOCAL_ROOT,
    SnapshotManagerTestHelper,
    create_source_dirs,
    make_snapshot,
    setup_test_dirs,
    teardown_test_dirs,
)


class TestSnapshotManagerCreate(SnapshotManagerTestHelper):
    def setUp(self):
        setup_test_dirs()
        self._src = create_source_dirs(SOURCE_DATA_PATH, ["m1", "m2", "m3"])

    def tearDown(self):
        teardown_test_dirs()

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

    def test_create_records_captured_size_and_utc_acquisition_interval(self):
        snap = make_snapshot("CapturedMetadata", self._src, n=1)
        created_at = snap.date_created
        source_file = self._src[0] / "m1_file.txt"
        source_file.write_bytes(b"changed after association construction")
        progress = []
        mgr = self._mgr(snap)

        mgr.create(progress_callback=progress.append)

        association = snap.directories[0]
        expected_bytes = sum(entry["size"] for entry in association.integrity_manifest.values() if entry["type"] == "file")
        self.assertEqual(association.mb_size, expected_bytes / (1024 * 1024))
        self.assertEqual(snap.date_created, created_at)
        self.assertIsNotNone(snap.capture_started_at)
        self.assertIsNotNone(snap.capture_completed_at)
        self.assertEqual(snap.capture_started_at.utcoffset().total_seconds(), 0)
        self.assertEqual(snap.capture_completed_at.utcoffset().total_seconds(), 0)
        self.assertLessEqual(snap.capture_started_at, snap.capture_completed_at)
        loaded = SnapshotSerializer.from_json(mgr.path_snapshot_json)
        self.assertEqual(loaded.capture_started_at, snap.capture_started_at)
        self.assertEqual(loaded.capture_completed_at, snap.capture_completed_at)
        self.assertEqual(loaded.directories[0].mb_size, association.mb_size)
        self.assertEqual(progress[-1], 100)

    def test_empty_association_reports_completion_and_zero_captured_size(self):
        empty_source = SOURCE_DATA_PATH / "empty_capture"
        empty_source.mkdir()
        snap = Snapshot(
            id="EmptyCapture",
            name="Empty capture",
            desc="",
            directories=[SnapDirAssociation(index=1, original_path=str(empty_source), folder_id="empty")],
        )
        progress = []

        self._mgr(snap).create(progress_callback=progress.append)

        self.assertEqual(progress, [100])
        self.assertEqual(snap.directories[0].mb_size, 0.0)

    def test_create_without_progress_observer_does_not_pre_scan_source_bytes(self):
        snap = make_snapshot("NoProgressScan", self._src, n=1)
        mgr = self._mgr(snap)

        with patch.object(SequentialFileCopyStrategy, "_total_bytes", side_effect=AssertionError("unneeded byte scan")):
            mgr.create()

        self.assertTrue(mgr.path_snapshot.is_dir())

    def test_create_rejects_linked_sources_before_publishing_a_snapshot(self):
        snap = make_snapshot("CreateWithSymlink", self._src, n=1)
        mgr = self._mgr(snap)
        outside = TEST_LOCAL_ROOT / "create_link_target"
        outside.mkdir()
        (outside / "important.txt").write_text("keep me", encoding="utf-8")
        link = self._src[0] / "linked-directory"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"Directory symlinks are unavailable: {error}")

        with self.assertRaisesRegex(ValueError, "symbolic link"):
            mgr.create()

        self.assertFalse(mgr.path_snapshot.exists())
        self.assertEqual((outside / "important.txt").read_text(encoding="utf-8"), "keep me")

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

    def test_create_uses_extended_metadata_mode_from_settings(self):
        snap = make_snapshot("ExtendedMetadata", self._src, n=1)
        source = Path(snap.directories[0].original_path)
        source.chmod(0o710)
        mgr = self._mgr(snap, SnapshotSettings(copy_metadata_mode=CopyMetadataMode.EXTENDED))

        mgr.create()

        stored_copy = mgr.path_snapshot / snap.directories[0].directory_name
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(stored_copy.stat().st_mode), stat.S_IMODE(source.stat().st_mode))

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
        self.assertEqual(set(CATALOGUE_PATH.iterdir()), {mgr.path_snapshot, CATALOGUE_PATH / ".pyliz_snapshot.lock"})

    def test_create_rejects_existing_snapshot_by_default(self):
        snap = make_snapshot("CreateConflict", self._src, n=1)
        mgr = self._mgr(snap)
        mgr.create()
        before = {p.relative_to(mgr.path_snapshot): p.read_bytes() for p in mgr.path_snapshot.rglob("*") if p.is_file()}
        (self._src[0] / "new.txt").write_text("new version")

        with self.assertRaises(FileExistsError):
            mgr.create()

        self.assertEqual({p.relative_to(mgr.path_snapshot): p.read_bytes() for p in mgr.path_snapshot.rglob("*") if p.is_file()}, before)
        self.assertEqual(set(CATALOGUE_PATH.iterdir()), {mgr.path_snapshot, CATALOGUE_PATH / ".pyliz_snapshot.lock"})

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
        self.assertEqual(set(CATALOGUE_PATH.iterdir()), {mgr.path_snapshot, CATALOGUE_PATH / ".pyliz_snapshot.lock"})

    def test_create_preserves_existing_snapshot_when_backup_rename_fails(self):
        snap = make_snapshot("RecreateBackupFail", self._src, n=1)
        mgr = self._mgr(snap)
        mgr.create()
        before = {p.relative_to(mgr.path_snapshot): p.read_bytes() for p in mgr.path_snapshot.rglob("*") if p.is_file()}

        with patch.object(Path, "rename", side_effect=PermissionError("backup rename denied")):
            with self.assertRaisesRegex(PermissionError, "backup rename denied"):
                mgr.create(replace_existing=True)

        self.assertEqual({p.relative_to(mgr.path_snapshot): p.read_bytes() for p in mgr.path_snapshot.rglob("*") if p.is_file()}, before)
        self.assertEqual(set(CATALOGUE_PATH.iterdir()), {mgr.path_snapshot, CATALOGUE_PATH / ".pyliz_snapshot.lock"})

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

        transaction = next((CATALOGUE_PATH / ".pyliz_transactions").iterdir())
        original = transaction / "original"
        prepared = transaction / "snapshot"
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
            """Interrupt only deletion of the old committed snapshot backup."""
            backup = Path(path)
            if backup.name == "original" and backup.parent.parent == mgr.path_catalogue / ".pyliz_transactions" and backup.is_dir():
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
        # The committed journal remains so a later catalogue scan can finish
        # removing this now partially deleted old tree.
        self.assertTrue((damaged_backups[0].parent / "journal.json").is_file())


class TestSnapshotManagerDelete(SnapshotManagerTestHelper):
    def setUp(self):
        setup_test_dirs()
        self._src = create_source_dirs(SOURCE_DATA_PATH, ["d1"])

    def tearDown(self):
        teardown_test_dirs()

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


class TestSnapshotManagerJsonUpdates(SnapshotManagerTestHelper):
    def setUp(self):
        setup_test_dirs()
        self._src = create_source_dirs(SOURCE_DATA_PATH, ["j1"])

    def tearDown(self):
        teardown_test_dirs()

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
        transaction_dir = mgr.path_catalogue / ".pyliz_transactions"
        self.assertFalse(transaction_dir.exists())
        self.assertFalse(mgr.path_snapshot.exists())


class TestSnapshotManagerDuplicate(SnapshotManagerTestHelper):
    def setUp(self):
        setup_test_dirs()
        self._src = create_source_dirs(SOURCE_DATA_PATH, ["dup1"])

    def tearDown(self):
        teardown_test_dirs()

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

    def test_duplicate_metadata_failure_does_not_publish_a_partial_snapshot(self):
        snap = make_snapshot("DupMetadataFailure", self._src, n=1)
        mgr = self._mgr(snap)
        mgr.create()
        original_id = snap.id
        duplicate_id = "duplicate-write-failed"
        metadata_paths = []
        real_to_json = SnapshotSerializer.to_json

        def fail_duplicate_metadata(snapshot, path):
            """Fail before replacement after the original tree has been staged."""
            if snapshot.id == duplicate_id:
                metadata_paths.append(Path(path))
                raise OSError("duplicate metadata write interrupted")
            return real_to_json(snapshot, path)

        with patch("pylizlib.core.os.snap.operations.lifecycle.gen_random_string", return_value=duplicate_id):
            with patch.object(SnapshotSerializer, "to_json", side_effect=fail_duplicate_metadata):
                with self.assertRaisesRegex(OSError, "duplicate metadata write interrupted"):
                    mgr.duplicate()

        duplicate_path = CATALOGUE_PATH / duplicate_id
        self.assertEqual(len(metadata_paths), 1)
        self.assertEqual(metadata_paths[0].parent.name, "snapshot")
        self.assertIn(".pyliz_transactions", metadata_paths[0].parts)
        self.assertFalse(duplicate_path.exists())
        self.assertEqual(SnapshotSerializer.from_json(mgr.path_snapshot_json).id, original_id)

        with patch("pylizlib.core.os.snap.operations.lifecycle.gen_random_string", return_value=duplicate_id):
            mgr.duplicate()
        self.assertEqual(SnapshotSerializer.from_json(duplicate_path / SnapshotSettings().json_filename).id, duplicate_id)

    def test_duplicate_raises_when_source_path_missing(self):
        snap = make_snapshot("DupMissing", self._src, n=1)
        mgr = self._mgr(snap)
        with self.assertRaises(FileNotFoundError):
            mgr.duplicate()
