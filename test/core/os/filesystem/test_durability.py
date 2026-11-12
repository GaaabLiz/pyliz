"""Rename visibility precedes directory flush attempts."""

from pylizlib.core.os.filesystem import durability


def test_rename_flushes_both_parents_after_publication(tmp_path, monkeypatch):
    """A namespace move is visible before either distinct parent is flushed."""
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    source = first / "entry"
    destination = second / "entry"
    source.write_bytes(b"contents")
    flushed = []

    def observe(path):
        """Record flushes only after the move has happened."""
        assert destination.read_bytes() == b"contents"
        assert not source.exists()
        flushed.append(path)
        return True

    monkeypatch.setattr(durability, "sync_directory", observe)
    durability.rename_and_sync(source, destination)
    assert set(flushed) == {first, second}


def test_unsupported_directory_sync_does_not_open_a_directory(tmp_path, monkeypatch):
    """The capability guard returns False without attempting unsupported I/O."""
    monkeypatch.setattr(durability.os, "O_DIRECTORY", 0, raising=False)
    assert durability.sync_directory(tmp_path) is False
