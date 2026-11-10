"""Unit tests for pluggable snapshot directory-copy strategies."""

import shutil
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from pylizlib.core.os.snap.copy_strategy import (
    DirectoryCopyStrategy,
    ProviderSnapshotCopyStrategy,
    SequentialFileCopyStrategy,
    SourceChangedError,
    SourceSnapshotProvider,
    VerifiedFileCopyStrategy,
)
from pylizlib.core.os.snap.domain import SnapshotSettings


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
        ProviderSnapshotCopyStrategy(CopyingSnapshotProvider()).copy_directory(self.source, destination)

        self.assertEqual((destination / "a.txt").read_text(), "old-a")
        self.assertEqual((destination / "b.txt").read_text(), "old-b")

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

        strategy = VerifiedFileCopyStrategy(max_attempts=5)
        configured = SnapshotSettings(copy_strategy=strategy)
        self.assertIs(configured.copy_strategy, strategy)

    def test_settings_reject_an_object_that_does_not_implement_the_interface(self):
        with self.assertRaises(TypeError):
            SnapshotSettings(copy_strategy=object())

    def test_copy_strategy_interface_is_abstract(self):
        with self.assertRaises(TypeError):
            DirectoryCopyStrategy()


if __name__ == "__main__":
    unittest.main()
