"""Tests for managing association identities and applying directory edits."""

import os
import shutil
from pathlib import Path
from unittest.mock import patch

from pylizlib.core.os.snap.domain import (
    SnapDirAssociation,
    SnapEditType,
    Snapshot,
)
from pylizlib.core.os.snap.manager import SnapshotManager
from pylizlib.core.os.snap.serializer import SnapshotSerializer
from pylizlib.core.os.snap.utils import SnapshotUtils
from test.core.os.snap.conftest import (
    CATALOGUE_PATH,
    SOURCE_DATA_PATH,
    SnapshotManagerTestHelper,
    create_source_dirs,
    make_snapshot,
    setup_test_dirs,
    teardown_test_dirs,
)


class TestSnapshotManagerDirectoryManagement(SnapshotManagerTestHelper):
    def setUp(self):
        setup_test_dirs()
        self._src = create_source_dirs(SOURCE_DATA_PATH, ["dm1", "dm2"])

    def tearDown(self):
        teardown_test_dirs()

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

    def test_associations_with_same_basename_and_index_use_distinct_storage_paths(self):
        sources = []
        for parent, value in (("first", "first copy"), ("second", "second copy")):
            source = SOURCE_DATA_PATH / parent / "data"
            source.mkdir(parents=True)
            (source / "value.txt").write_text(value, encoding="utf-8")
            sources.append(source)

        snap = Snapshot(
            id="SameIndexNames",
            name="Same index names",
            desc="",
            directories=[SnapDirAssociation(index=1, original_path=str(source), folder_id=f"assoc-{index}") for index, source in enumerate(sources)],
        )
        mgr = self._mgr(snap)
        mgr.create()

        names = [association.directory_name for association in snap.directories]
        self.assertEqual(len(set(names)), 2)
        self.assertEqual((mgr.path_snapshot / names[0] / "value.txt").read_text(encoding="utf-8"), "first copy")
        self.assertEqual((mgr.path_snapshot / names[1] / "value.txt").read_text(encoding="utf-8"), "second copy")

    def test_install_after_reload_uses_a_free_index_and_preserves_both_same_basename_copies(self):
        first_source = SOURCE_DATA_PATH / "first" / "data"
        first_source.mkdir(parents=True)
        (first_source / "value.txt").write_text("first copy", encoding="utf-8")
        snap = Snapshot(
            id="RestartIndex",
            name="Restart index",
            desc="",
            directories=[SnapDirAssociation(index=1, original_path=str(first_source), folder_id="existing-id")],
        )
        original_manager = self._mgr(snap)
        original_manager.create()
        original_name = snap.directories[0].directory_name

        second_source = SOURCE_DATA_PATH / "second" / "data"
        second_source.mkdir(parents=True)
        (second_source / "value.txt").write_text("second copy", encoding="utf-8")

        with patch.object(SnapDirAssociation, "_current_index", 0):
            restarted_snapshot = SnapshotSerializer.from_json(original_manager.path_snapshot_json)
            restarted_manager = self._mgr(restarted_snapshot)
            with patch(
                "pylizlib.core.os.snap.manager.gen_random_string",
                side_effect=["existing-id", "new-id"],
            ):
                restarted_manager.install_directory(second_source)

        self.assertEqual([association.index for association in restarted_snapshot.directories], [1, 2])
        added = restarted_snapshot.directories[1]
        self.assertEqual(added.folder_id, "new-id")
        self.assertNotEqual(added.directory_name, original_name)
        self.assertEqual((restarted_manager.path_snapshot / original_name / "value.txt").read_text(encoding="utf-8"), "first copy")
        self.assertEqual((restarted_manager.path_snapshot / added.directory_name / "value.txt").read_text(encoding="utf-8"), "second copy")
        reloaded = SnapshotSerializer.from_json(restarted_manager.path_snapshot_json)
        self.assertEqual([association.directory_name for association in reloaded.directories], [original_name, added.directory_name])

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

        with patch("pylizlib.core.os.filesystem.directories.shutil.rmtree", side_effect=PermissionError("association is locked")):
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


class TestSnapshotManagerUpdateAssocDirs(SnapshotManagerTestHelper):
    def setUp(self):
        setup_test_dirs()
        self._src = create_source_dirs(SOURCE_DATA_PATH, ["ua1"])

    def tearDown(self):
        teardown_test_dirs()

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
        expected_bytes = sum(entry["size"] for entry in loaded.directories[0].integrity_manifest.values() if entry["type"] == "file")
        self.assertEqual(loaded.directories[0].mb_size, expected_bytes / (1024 * 1024))
        self.assertIsNotNone(loaded.capture_started_at)
        self.assertIsNotNone(loaded.capture_completed_at)
        self.assertEqual(loaded.capture_started_at.utcoffset().total_seconds(), 0)
        self.assertEqual(loaded.capture_completed_at.utcoffset().total_seconds(), 0)
        self.assertLessEqual(loaded.capture_started_at, loaded.capture_completed_at)

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


class TestSnapshotManagerDirectoryActions(SnapshotManagerTestHelper):
    def setUp(self):
        setup_test_dirs()
        self._src = create_source_dirs(SOURCE_DATA_PATH, ["ab1", "ab2", "ab3"])

    def tearDown(self):
        teardown_test_dirs()

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

    def test_remove_and_renumber_same_name_preserves_kept_copy_path(self):
        snap = self._create_same_name_snapshot()
        kept_dir_name = snap.directories[1].directory_name
        new = snap.clone()
        new.directories.pop(0)
        new.directories[0].index = 1
        mgr = self._mgr(new)

        edits = SnapshotUtils.get_edits_between_snapshots(snap, new)
        mgr.update_from_actions_list(edits)

        self.assertEqual(new.directories[0].directory_name, kept_dir_name)
        self.assertEqual((mgr.path_snapshot / kept_dir_name / "foo_file.txt").read_text(), "saved copy 1")
        self.assertTrue((mgr.path_snapshot / "snapshot.json").is_file())
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
        self.assertEqual(
            {p.name for p in mgr.path_snapshot.iterdir()},
            {*(association.directory_name for association in new.directories), "snapshot.json", ".snapshot.json.previous"},
        )

    def test_duplicate_presentation_indices_do_not_collide_on_disk(self):
        snap = self._create_same_name_snapshot()
        new = snap.clone()
        new.directories[1].index = 1
        mgr = self._mgr(new)
        edits = SnapshotUtils.get_edits_between_snapshots(snap, new)
        self.assertEqual(edits, [])
        self.assertEqual(len({association.directory_name for association in new.directories}), 2)
        mgr.update_from_actions_list(edits)
        for index, association in enumerate(new.directories):
            self.assertEqual((mgr.path_snapshot / association.directory_name / "foo_file.txt").read_text(), f"saved copy {index}")

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
        # Presentation index changes do not rename the stable physical copy.
        self.assertEqual(len(edits), 2)
        self.assertFalse(any(e.action_type == SnapEditType.RENAME_DIR for e in edits))

        mgr2 = SnapshotManager(snap_new, CATALOGUE_PATH)
        mgr2.update_from_actions_list(edits)

        self.assertFalse((mgr.path_snapshot / removed_assoc.directory_name).exists())
        self.assertTrue((mgr.path_snapshot / snap_new.directories[-1].directory_name).exists())
        self.assertEqual(old_kept_dir_name, new_kept_dir_name)
        self.assertTrue((mgr.path_snapshot / new_kept_dir_name).exists())
