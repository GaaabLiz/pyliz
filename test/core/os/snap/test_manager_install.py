"""Tests for installing, synchronizing, and removing associated copies."""

import shutil
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

from pylizlib.core.data.gen import gen_random_string
from pylizlib.core.log.pylizLogger import logger
from pylizlib.core.os.snap.catalogue import SnapshotCatalogue
from pylizlib.core.os.snap.domain import (
    SnapDirAssociation,
    Snapshot,
    SnapshotSettings,
)
from pylizlib.core.os.snap.integrity import SnapshotIntegrityError
from pylizlib.core.os.snap.manager import SnapshotManager
from pylizlib.core.os.snap.serializer import SnapshotSerializer
from test.core.os.snap.conftest import (
    CATALOGUE_PATH,
    SOURCE_DATA_PATH,
    TEST_LOCAL_ROOT,
    SnapshotManagerTestHelper,
    create_source_dirs,
    make_snapshot,
    reset_index,
    setup_test_dirs,
    teardown_test_dirs,
)


class TestSnapshotManagerInstall(SnapshotManagerTestHelper):
    def setUp(self):
        setup_test_dirs()
        self._src = create_source_dirs(SOURCE_DATA_PATH, ["i1"])

    def tearDown(self):
        teardown_test_dirs()

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

    def test_remove_preflights_all_paths_before_deleting_any_copy(self):
        safe_path = TEST_LOCAL_ROOT / "safe_copy_before_critical"
        safe_path.mkdir(parents=True)
        (safe_path / "keep.txt").write_text("keep")
        snap = Snapshot(
            id=gen_random_string(8),
            name="BulkCriticalRemoval",
            desc="",
            directories=[
                SnapDirAssociation(index=1, original_path=str(safe_path), folder_id="safe-removal"),
                SnapDirAssociation(index=2, original_path="/usr/bin/test", folder_id="critical-removal"),
            ],
        )
        mgr = self._mgr(snap)

        with self.assertRaisesRegex(ValueError, "critical system path"):
            mgr.remove_installed_copies()

        self.assertEqual((safe_path / "keep.txt").read_text(), "keep")

    def test_install_rejects_destinations_overlapping_catalogue(self):
        snap = make_snapshot("InstallCatalogueOverlap", self._src, n=1)
        mgr = self._mgr(snap)
        mgr.create()
        internal_copy = mgr.path_snapshot / snap.directories[0].directory_name
        snap.directories[0].original_path = str(internal_copy / "would_replace_catalogue_data")

        with self.assertRaisesRegex(ValueError, "overlaps the snapshot catalogue"):
            mgr.install()

        self.assertTrue((internal_copy / "i1_file.txt").is_file())
        self.assertFalse((mgr.path_snapshot / ".pyliz_transactions").exists())

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


class TestSnapshotManagerWindowsPermissions(SnapshotManagerTestHelper):
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


class TestSnapshotManagerInstallFailurePaths(SnapshotManagerTestHelper):
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
