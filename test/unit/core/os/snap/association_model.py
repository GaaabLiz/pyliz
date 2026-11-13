"""Only copies owned by the current association call may be cleaned up."""

import pytest

from pylizlib.core.os.snap import DirectoryCopyStrategy, SequentialFileCopyStrategy, SnapDirAssociation


def test_repeating_an_association_copy_preserves_the_previous_copy(tmp_path):
    """A refused second copy leaves the first directory and its bytes untouched."""
    source = tmp_path / "source"
    source.mkdir()
    (source / "payload").write_bytes(b"original captured data")
    association = SnapDirAssociation(0, str(source), "identity")
    parent = tmp_path / "stored"
    association.copy_install_to(parent)
    destination = parent / association.directory_name
    before = (destination / "payload").stat()
    (source / "payload").write_bytes(b"changed live source")

    with pytest.raises(FileExistsError):
        association.copy_install_to(parent)

    assert (destination / "payload").read_bytes() == b"original captured data"
    assert (destination / "payload").stat().st_mtime_ns == before.st_mtime_ns


@pytest.mark.parametrize("delegate_returns", [False, True])
def test_destination_created_by_another_actor_is_never_removed(tmp_path, delegate_returns):
    """Both delegate failure and final publication conflict preserve foreign data."""
    source = tmp_path / "source"
    source.mkdir()
    (source / "payload").write_bytes(b"source data")
    association = SnapDirAssociation(0, str(source), "identity")
    parent = tmp_path / "stored"
    final_path = parent / association.directory_name

    class RacingStrategy(SequentialFileCopyStrategy):
        """Create a competing final destination while this copy is in progress."""

        def copy_directory(self, source, destination, *args, **kwargs):
            """Place foreign bytes outside this invocation's private copy."""
            if delegate_returns:
                super().copy_directory(source, destination, *args, **kwargs)
            final_path.mkdir(parents=True, exist_ok=True)
            (final_path / "foreign").write_bytes(b"another writer owns this data")
            if not delegate_returns:
                raise FileExistsError("concurrent destination")
            return destination

    with pytest.raises(FileExistsError):
        association.copy_install_to(parent, copy_strategy=RacingStrategy())
    assert (final_path / "foreign").read_bytes() == b"another writer owns this data"
    assert not list(parent.glob(".association_copy_*"))


def test_custom_strategy_partial_copy_is_cleaned_in_its_private_workspace(tmp_path):
    """Legacy delegates may leave partial files without exposing or deleting targets."""
    source = tmp_path / "source"
    source.mkdir()
    association = SnapDirAssociation(0, str(source), "identity")
    parent = tmp_path / "stored"

    class FailingStrategy(DirectoryCopyStrategy):
        """Leave partial contents to exercise association-owned staging cleanup."""

        def copy_directory(self, source, destination, *args, **kwargs):
            """Create a partial tree and fail with the delegate's original error."""
            destination.mkdir()
            (destination / "partial").write_bytes(b"partial")
            raise OSError("copy interrupted")

    with pytest.raises(OSError, match="copy interrupted"):
        association.copy_install_to(parent, copy_strategy=FailingStrategy())
    assert not list(parent.iterdir())


def test_failed_publication_does_not_publish_manifest_or_model_changes(tmp_path):
    """Successful private copying is not yet a successful association publication."""
    source = tmp_path / "source"
    source.mkdir()
    (source / "payload").write_bytes(b"content")
    association = SnapDirAssociation(0, str(source), "identity")
    parent = tmp_path / "stored"
    final_path = parent / association.directory_name
    output = {".": {"type": "directory", "size": 0, "sha256": None}}

    class ConflictingStrategy(SequentialFileCopyStrategy):
        """Complete a private manifest before a competing publication appears."""

        def copy_directory(self, source, destination, *args, **kwargs):
            """Return copied contents while preserving independently created final data."""
            copied = super().copy_directory(source, destination, *args, **kwargs)
            final_path.mkdir()
            (final_path / "foreign").write_bytes(b"keep")
            return copied

    with pytest.raises(FileExistsError):
        association.copy_install_to(parent, copy_strategy=ConflictingStrategy(), manifest=output)
    assert output == {".": {"type": "directory", "size": 0, "sha256": None}}
    assert association.integrity_manifest is None
    assert association.mb_size is None
    assert (final_path / "foreign").read_bytes() == b"keep"
