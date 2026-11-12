"""Consistency and metadata policies share a source lifetime without concrete coupling."""

import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path

import pytest

from pylizlib.core.os.snap.copy_strategy import DirectoryCopyStrategy, ExtendedMetadataCopyStrategy, ProviderSnapshotCopyStrategy, SourceSnapshotProvider


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
