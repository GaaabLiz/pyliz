"""Metadata collaborators rely on capabilities rather than adapter keyword names."""

from pathlib import Path

from pylizlib.core.os.snap.domain import Snapshot, SnapshotSettings
from pylizlib.core.os.snap.serializer import SnapshotSerializer
from pylizlib.core.os.snap.storage.context import SnapshotMetadata, SnapshotStorage


class NamedMetadataAdapter:
    """Use different argument names while retaining the serializer's behavior."""

    def to_json(self, model: Snapshot, filename: Path) -> None:
        """Save the supplied model to this adapter's filename argument."""
        SnapshotSerializer.to_json(model, filename)

    def from_json(self, filename: Path) -> Snapshot:
        """Load the adapter's filename without requiring a path keyword."""
        return SnapshotSerializer.from_json(filename)

    def read_bytes(self, filename: Path) -> bytes:
        """Read exact bytes through the same protected serializer."""
        return SnapshotSerializer.read_bytes(filename)

    def write_bytes(self, filename: Path, data: bytes) -> None:
        """Restore exact bytes through the same protected serializer."""
        SnapshotSerializer.write_bytes(filename, data)

    def update_field(self, filename: Path, key: str, value) -> None:
        """Patch one raw metadata field without rebuilding the domain model."""
        SnapshotSerializer.update_field(filename, key, value)


def test_storage_accepts_metadata_adapters_with_their_own_keyword_names(tmp_path):
    """Both the serializer class and an instance satisfy positional capabilities."""
    adapter: SnapshotMetadata = NamedMetadataAdapter()
    snapshot = Snapshot("identity", "name", "description")
    settings = SnapshotSettings()
    root = tmp_path / snapshot.folder_name
    root.mkdir()
    metadata = root / settings.json_filename
    default = SnapshotStorage(snapshot, settings, tmp_path, root, metadata).metadata
    assert default is SnapshotSerializer
    storage = SnapshotStorage(snapshot, settings, tmp_path, root, metadata, adapter)
    storage.save_json()
    original = adapter.read_bytes(metadata)
    adapter.update_field(metadata, "name", "changed")
    assert adapter.from_json(metadata).name == "changed"
    adapter.write_bytes(metadata, original)
    assert default.from_json(metadata).name == "name"
