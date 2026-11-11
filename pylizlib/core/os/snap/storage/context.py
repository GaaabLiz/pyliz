"""Explicit storage dependencies shared by the single-snapshot operations."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pylizlib.core.os.snap.domain import Snapshot, SnapshotSettings
from pylizlib.core.os.snap.serializer import SnapshotSerializer
from pylizlib.core.os.snap.storage.paths import get_snapshot_child_path, validate_snapshot_root


class SnapshotMetadata(Protocol):
    """Persistence operations needed by snapshot publication and recovery.

    The default adapter is SnapshotSerializer itself. Raw-byte access is part
    of this contract because an edit rollback restores the original JSON bytes
    rather than regenerating potentially different metadata from a model.
    """

    def to_json(self, snapshot: Snapshot, path: Path) -> None:
        """Validate and persist the complete snapshot using its existing format."""
        ...

    def from_json(self, path: Path) -> Snapshot:
        """Read persisted metadata with its legacy defaults and validation."""
        ...

    def read_bytes(self, path: Path) -> bytes:
        """Read the exact file contents for recovery without following links."""
        ...

    def write_bytes(self, path: Path, contents: bytes) -> None:
        """Restore exact metadata bytes using protected file access."""
        ...

    def update_field(self, path: Path, field_name: str, new_value) -> None:
        """Update a raw JSON field without discarding unknown extension fields."""
        ...


@dataclass
class SnapshotStorage:
    """Live model and storage paths for one invocation of a manager operation.

    Facades construct this context from their current public attributes on each
    call. Paths retain the manager's originally captured values, so changing an
    ID or JSON filename is detected instead of silently redirecting writes.
    Constructing this context performs no I/O and no extra model validation.
    """

    snapshot: Snapshot
    settings: SnapshotSettings
    path_catalogue: Path
    path_snapshot: Path
    path_snapshot_json: Path
    metadata: SnapshotMetadata = SnapshotSerializer

    def root_path(self) -> Path:
        """Revalidate the root and reject an ID changed after manager creation."""
        root = validate_snapshot_root(self.snapshot.folder_name, self.path_catalogue)
        if root != self.path_snapshot:
            raise ValueError("The snapshot ID changed after the manager was initialized.")
        return root

    def child_path(self, name: str) -> Path:
        """Validate the mutable model and resolve one direct stored child."""
        self.snapshot.validate()
        path = get_snapshot_child_path(self.snapshot.folder_name, self.path_catalogue, name)
        if path.parent != self.path_snapshot:
            raise ValueError("The snapshot ID changed after the manager was initialized.")
        return path

    def save_json(self) -> None:
        """Save only to the metadata path captured when the manager was created."""
        json_path = self.child_path(self.settings.json_filename)
        if json_path != self.path_snapshot_json:
            raise ValueError("The snapshot JSON path changed after the manager was initialized.")
        self.metadata.to_json(self.snapshot, json_path)
