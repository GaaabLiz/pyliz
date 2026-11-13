"""Unit tests for pluggable snapshot directory-copy strategies."""

import os
import shutil
import stat
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

from pylizlib.core.os.snap.copy_strategy import (
    CopyMetadataMode,
    DirectoryCopyStrategy,
    ExtendedMetadataCopyStrategy,
    ProviderSnapshotCopyStrategy,
    SequentialFileCopyStrategy,
    SourceChangedError,
    SourceSnapshotProvider,
    VerifiedFileCopyStrategy,
)
from pylizlib.core.os.snap.domain import SnapshotSettings
from pylizlib.core.os.snap.integrity import SnapshotIntegrityError


class InterleavingCopyStrategy(SequentialFileCopyStrategy):
    """Recreate an impossible mixed tree on the first copy attempt."""

    def __init__(self, observed_source_states: list[tuple[str, str]]):
        self.calls = 0
        self.observed_source_states = observed_source_states

    def copy_directory(self, source, destination, progress_callback=None, message_callback=None):
        self.calls += 1
        source = Path(source)
        destination = Path(destination)
        if self.calls == 1:
            destination.mkdir(parents=True)
            shutil.copy2(source / "a.txt", destination / "a.txt")
            (source / "a.txt").write_text("new-a", encoding="utf-8")
            self.observed_source_states.append(((source / "a.txt").read_text(), (source / "b.txt").read_text()))
            (source / "b.txt").write_text("new-b", encoding="utf-8")
            self.observed_source_states.append(((source / "a.txt").read_text(), (source / "b.txt").read_text()))
            shutil.copy2(source / "b.txt", destination / "b.txt")
            return destination
        return super().copy_directory(source, destination, progress_callback, message_callback)


class ChangingCopyStrategy(SequentialFileCopyStrategy):
    def __init__(self):
        self.calls = 0

    def copy_directory(self, source, destination, progress_callback=None, message_callback=None):
        result = super().copy_directory(source, destination, progress_callback, message_callback)
        self.calls += 1
        (Path(source) / "value.txt").write_text(f"version-{self.calls}", encoding="utf-8")
        return result


class TestDirectoryCopyStrategies(unittest.TestCase):
    def setUp(self):
        self._temporary = tempfile.TemporaryDirectory()
        self.root = Path(self._temporary.name)
        self.source = self.root / "source"
        self.source.mkdir()
        (self.source / "a.txt").write_text("old-a", encoding="utf-8")
        (self.source / "b.txt").write_text("old-b", encoding="utf-8")

    def tearDown(self):
        self._temporary.cleanup()

    def test_sequential_strategy_copies_contents_and_reports_progress(self):
        destination = self.root / "sequential-copy"
        progress = []
        messages = []

        result = SequentialFileCopyStrategy().copy_directory(
            self.source,
            destination,
            progress_callback=lambda copied, total: progress.append((copied, total)),
            message_callback=messages.append,
        )

        self.assertEqual(result, destination)
        self.assertEqual((destination / "a.txt").read_text(), "old-a")
        self.assertEqual((destination / "b.txt").read_text(), "old-b")
        self.assertEqual(progress[-1], (10, 10))
        self.assertEqual(len(messages), 2)

    def test_sequential_strategy_rejects_file_directory_broken_and_cyclic_links(self):
        outside = self.root / "outside"
        outside.mkdir()
        important = outside / "important.txt"
        important.write_text("keep me", encoding="utf-8")
        links = (
            ("file-link", important, False),
            ("directory-link", outside, True),
            ("broken-link", self.root / "missing", False),
            ("cycle-link", self.source, True),
        )

        for name, target, is_directory in links:
            with self.subTest(name=name):
                link = self.source / name
                try:
                    link.symlink_to(target, target_is_directory=is_directory)
                except OSError as error:
                    self.skipTest(f"symlink creation is unavailable: {error}")

                destination = self.root / f"copy-{name}"
                with self.assertRaisesRegex(ValueError, "symbolic link"):
                    SequentialFileCopyStrategy().copy_directory(self.source, destination)

                self.assertFalse(destination.exists())
                self.assertEqual(important.read_text(encoding="utf-8"), "keep me")
                link.unlink()

    def test_verified_and_provider_strategies_reject_source_links(self):
        class ExistingTreeProvider(SourceSnapshotProvider):
            @contextmanager
            def create_snapshot(provider_self, source):
                yield Path(source)

        link = self.source / "directory-link"
        try:
            link.symlink_to(self.root, target_is_directory=True)
        except OSError as error:
            self.skipTest(f"symlink creation is unavailable: {error}")

        for strategy in (VerifiedFileCopyStrategy(), ProviderSnapshotCopyStrategy(ExistingTreeProvider())):
            with self.subTest(strategy=type(strategy).__name__):
                destination = self.root / f"copy-{type(strategy).__name__}"
                with self.assertRaisesRegex(ValueError, "symbolic link"):
                    strategy.copy_directory(self.source, destination)
                self.assertFalse(destination.exists())

    def test_extended_metadata_strategy_preserves_root_attributes_and_internal_hardlinks(self):
        payload = self.source / "a.txt"
        hardlink = self.source / "b.txt"
        hardlink.unlink()
        try:
            os.link(payload, hardlink)
        except OSError as error:
            self.skipTest(f"Hard links are unavailable: {error}")
        self.source.chmod(0o710)
        expected_mtime_ns = 1_650_000_000_000_000_000
        os.utime(self.source, ns=(expected_mtime_ns, expected_mtime_ns))

        settings = SnapshotSettings(copy_metadata_mode=CopyMetadataMode.EXTENDED)
        self.assertIsInstance(settings.copy_strategy, ExtendedMetadataCopyStrategy)
        destination = self.root / "extended-copy"
        settings.copy_strategy.copy_directory(self.source, destination)

        self.assertEqual(destination.stat().st_mtime_ns, expected_mtime_ns)
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(destination.stat().st_mode), stat.S_IMODE(self.source.stat().st_mode))
        self.assertTrue(os.path.samefile(destination / "a.txt", destination / "b.txt"))
        self.assertFalse(os.path.samefile(self.source / "a.txt", destination / "a.txt"))

    def test_extended_metadata_strategy_copies_available_extended_attributes(self):
        if not all(hasattr(os, name) for name in ("setxattr", "getxattr")):
            self.skipTest("Extended attributes are unavailable")
        attribute_name = "user.pyliz_snapshot_test"
        source_file = self.source / "a.txt"
        try:
            os.setxattr(source_file, attribute_name, b"metadata")
        except OSError as error:
            self.skipTest(f"Extended attributes are unavailable on this filesystem: {error}")

        destination = self.root / "extended-xattr-copy"
        SnapshotSettings(copy_metadata_mode=CopyMetadataMode.EXTENDED).copy_strategy.copy_directory(self.source, destination)

        self.assertEqual(os.getxattr(destination / "a.txt", attribute_name), b"metadata")

    def test_extended_attribute_copy_uses_platform_attribute_apis(self):
        source = self.root / "xattr-source"
        destination = self.root / "xattr-destination"
        with (
            patch("pylizlib.core.os.filesystem.metadata.os.listxattr", return_value=["user.sample"], create=True),
            patch("pylizlib.core.os.filesystem.metadata.os.getxattr", return_value=b"value", create=True),
            patch("pylizlib.core.os.filesystem.metadata.os.setxattr", create=True) as set_xattr,
        ):
            ExtendedMetadataCopyStrategy._copy_extended_attributes(source, destination)

        set_xattr.assert_called_once_with(destination, "user.sample", b"value", follow_symlinks=False)

    def test_extended_metadata_failure_does_not_publish_a_partial_copy(self):
        strategy = ExtendedMetadataCopyStrategy(SequentialFileCopyStrategy())
        destination = self.root / "extended-failed-copy"

        with patch("pylizlib.core.os.snap.copy_strategy.ExtendedMetadataCopyStrategy._preserve_metadata", side_effect=OSError("metadata denied")):
            with self.assertRaisesRegex(OSError, "metadata denied"):
                strategy.copy_directory(self.source, destination)

        self.assertFalse(destination.exists())
        self.assertFalse(list(self.root.glob(".extended_metadata_*")))

    def test_sequential_strategy_records_and_checks_a_content_manifest(self):
        (self.source / "empty").mkdir()
        manifest = {}
        destination = self.root / "manifest-copy"
        SequentialFileCopyStrategy().copy_directory(self.source, destination, manifest=manifest)

        self.assertEqual(manifest["."]["type"], "directory")
        self.assertEqual(manifest["empty"], {"type": "directory", "size": 0, "sha256": None})
        self.assertEqual(manifest["a.txt"]["size"], 5)
        self.assertRegex(manifest["a.txt"]["sha256"], r"^[0-9a-f]{64}$")

        (destination / "a.txt").write_text("bad-a", encoding="utf-8")
        with self.assertRaises(SnapshotIntegrityError):
            SequentialFileCopyStrategy().copy_directory(
                destination,
                self.root / "verified-copy",
                expected_manifest=manifest,
            )

    def test_manifest_verification_detects_missing_files_before_publication(self):
        manifest = {}
        destination = self.root / "manifest-copy"
        SequentialFileCopyStrategy().copy_directory(self.source, destination, manifest=manifest)
        (destination / "a.txt").unlink()

        published = self.root / "failed-verified-copy"
        with self.assertRaises(SnapshotIntegrityError):
            SequentialFileCopyStrategy().copy_directory(destination, published, expected_manifest=manifest)
        self.assertFalse(published.exists())

    def test_verified_strategy_retries_an_unobservable_mixed_copy(self):
        observed_states = [("old-a", "old-b")]
        delegate = InterleavingCopyStrategy(observed_states)
        destination = self.root / "verified-copy"

        VerifiedFileCopyStrategy(max_attempts=2, delegate=delegate).copy_directory(self.source, destination)

        self.assertNotIn(("old-a", "new-b"), observed_states)
        self.assertEqual((destination / "a.txt").read_text(), "new-a")
        self.assertEqual((destination / "b.txt").read_text(), "new-b")
        self.assertEqual(delegate.calls, 2)

    def test_verified_strategy_fails_without_publishing_after_repeated_changes(self):
        destination = self.root / "unstable-copy"
        delegate = ChangingCopyStrategy()

        with self.assertRaises(SourceChangedError):
            VerifiedFileCopyStrategy(max_attempts=2, delegate=delegate).copy_directory(self.source, destination)

        self.assertFalse(destination.exists())
        self.assertEqual(delegate.calls, 2)
        self.assertFalse(list(self.root.glob(".verified_copy_*")))

    def test_verified_strategy_returns_manifest_from_the_published_copy(self):
        manifest = {}
        destination = self.root / "verified-manifest-copy"
        VerifiedFileCopyStrategy().copy_directory(self.source, destination, manifest=manifest)

        self.assertEqual(manifest["a.txt"]["size"], 5)
        self.assertEqual(manifest["a.txt"]["sha256"], VerifiedFileCopyStrategy._manifest(destination)["a.txt"][0])

    def test_snapshot_provider_strategy_copies_from_the_frozen_tree(self):
        class CopyingSnapshotProvider(SourceSnapshotProvider):
            @contextmanager
            def create_snapshot(provider_self, source):
                with tempfile.TemporaryDirectory() as temporary_directory:
                    frozen = Path(temporary_directory) / "frozen"
                    shutil.copytree(source, frozen)
                    (Path(source) / "a.txt").write_text("changed-after-freeze", encoding="utf-8")
                    yield frozen

        destination = self.root / "provider-copy"
        manifest = {}
        ProviderSnapshotCopyStrategy(CopyingSnapshotProvider()).copy_directory(self.source, destination, manifest=manifest)

        self.assertEqual((destination / "a.txt").read_text(), "old-a")
        self.assertEqual((destination / "b.txt").read_text(), "old-b")
        self.assertEqual(manifest["a.txt"]["size"], 5)

    def test_extended_metadata_uses_the_provider_snapshot_not_the_live_source(self):
        expected_mtime_ns = 1_650_000_000_000_000_000

        class MetadataSnapshotProvider(SourceSnapshotProvider):
            @contextmanager
            def create_snapshot(provider_self, source):
                with tempfile.TemporaryDirectory() as temporary_directory:
                    frozen = Path(temporary_directory) / "frozen"
                    shutil.copytree(source, frozen)
                    frozen.chmod(0o711)
                    os.utime(frozen, ns=(expected_mtime_ns, expected_mtime_ns))
                    Path(source).chmod(0o755)
                    os.utime(Path(source), ns=(expected_mtime_ns + 1_000_000_000, expected_mtime_ns + 1_000_000_000))
                    yield frozen

        provider_strategy = ProviderSnapshotCopyStrategy(MetadataSnapshotProvider())
        settings = SnapshotSettings(copy_strategy=provider_strategy, copy_metadata_mode=CopyMetadataMode.EXTENDED)
        destination = self.root / "provider-extended-copy"
        settings.copy_strategy.copy_directory(self.source, destination)

        self.assertEqual(destination.stat().st_mtime_ns, expected_mtime_ns)

    def test_snapshot_provider_strategy_rejects_a_symlinked_snapshot_root(self):
        link = self.root / "frozen-link"
        link.symlink_to(self.source, target_is_directory=True)

        class SymlinkSnapshotProvider(SourceSnapshotProvider):
            @contextmanager
            def create_snapshot(provider_self, source):
                yield link

        destination = self.root / "provider-copy"
        with self.assertRaises(NotADirectoryError):
            ProviderSnapshotCopyStrategy(SymlinkSnapshotProvider()).copy_directory(self.source, destination)

        self.assertFalse(destination.exists())

    def test_snapshot_settings_defaults_to_sequential_and_accepts_a_strategy(self):
        settings = SnapshotSettings()
        self.assertIsInstance(settings.copy_strategy, SequentialFileCopyStrategy)
        self.assertIs(settings.copy_metadata_mode, CopyMetadataMode.BASIC)

        strategy = VerifiedFileCopyStrategy(max_attempts=5)
        configured = SnapshotSettings(copy_strategy=strategy)
        self.assertIs(configured.copy_strategy, strategy)

    def test_settings_reject_an_object_that_does_not_implement_the_interface(self):
        with self.assertRaises(TypeError):
            SnapshotSettings(copy_strategy=object())

    def test_copy_strategy_interface_is_abstract(self):
        with self.assertRaises(TypeError):
            DirectoryCopyStrategy()


@pytest.mark.parametrize("metadata_fails", [False, True])
def test_metadata_finishes_inside_provider_context_with_legacy_delegate(tmp_path, monkeypatch, metadata_fails):
    """Provider cleanup follows metadata, including errors; legacy delegates need no kwargs."""
    source = tmp_path / "source"
    source.mkdir()
    (source / "content").write_text("captured")
    destination = tmp_path / "destination"
    events = []
    state = {"active": False}

    class Provider(SourceSnapshotProvider):
        """Supply a disposable frozen copy while mutating the original live source."""

        @contextmanager
        def create_snapshot(self, source):
            """Keep the frozen source alive until all requested metadata completes."""
            with tempfile.TemporaryDirectory() as directory:
                frozen = Path(directory) / "frozen"
                shutil.copytree(source, frozen)
                (source / "content").write_text("changed")
                state["active"] = True
                state["source"] = frozen
                events.append("open")
                try:
                    yield frozen
                finally:
                    state["active"] = False
                    events.append("close")

    class LegacyCopy(DirectoryCopyStrategy):
        """Implement only the historical four-positional-argument copy contract."""

        def copy_directory(self, source, destination, progress_callback=None, message_callback=None):
            """Copy bytes while the provider context is held."""
            assert state["active"]
            shutil.copytree(source, destination)
            return destination

    def preserve(actual_source, staged):
        """Require the frozen source and simulate an optional metadata failure."""
        assert state["active"]
        assert actual_source == state["source"]
        assert (staged / "content").read_text() == "captured"
        events.append("metadata")
        if metadata_fails:
            raise OSError("metadata failed")

    monkeypatch.setattr(ExtendedMetadataCopyStrategy, "_preserve_metadata", staticmethod(preserve))
    strategy = ExtendedMetadataCopyStrategy(ProviderSnapshotCopyStrategy(Provider(), LegacyCopy()))
    if metadata_fails:
        with pytest.raises(OSError, match="metadata failed"):
            strategy.copy_directory(source, destination)
        assert not destination.exists()
    else:
        strategy.copy_directory(source, destination)
        assert (destination / "content").read_text() == "captured"
    assert events == ["open", "metadata", "close"]
    assert not state["active"]
    assert not state["source"].exists()


if __name__ == "__main__":
    unittest.main()
