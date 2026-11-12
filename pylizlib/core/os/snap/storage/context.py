"""Explicit storage dependencies shared by the single-snapshot operations."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

from pylizlib.core.os.snap.domain import Snapshot, SnapshotSettings
from pylizlib.core.os.snap.serializer import SnapshotSerializer
from pylizlib.core.os.snap.storage.paths import get_snapshot_child_path, validate_snapshot_root


class SnapshotMetadata(Protocol):
    """Persistence operations needed by snapshot publication and recovery.

    The default adapter is SnapshotSerializer itself, whose writes use atomic
    same-directory publication and a previous-version sidecar. Alternate
    adapters are responsible for equivalent write safety. A successful rename
    still cannot prove remote-server stable-media persistence. Raw-byte access
    is part of this contract because an edit rollback restores the original
    JSON bytes rather than regenerating potentially different metadata.

    Parameters are positional-only in this capability contract: adapters may
    retain their own public keyword names, such as the serializer's filepath.
    """

    def to_json(self, snapshot: Snapshot, path: Path, /) -> None:
        """Validate and persist the complete snapshot using its existing format.

        Args:
            snapshot (Snapshot): Snapshot model used or mutated by this operation; association identities are retained
                where documented.
            path (Path): Native filesystem entry operated on by this method.

        Returns:
            None: No return value.
        """
        ...

    def from_json(self, path: Path, /) -> Snapshot:
        """Read persisted metadata with its legacy defaults and validation.

        Args:
            path (Path): Native filesystem entry operated on by this method.

        Returns:
            Snapshot: Validated Snapshot using legacy date/default handling; loading never scans source directories
                for sizes.
        """
        ...

    def read_bytes(self, path: Path, /) -> bytes:
        """Read the exact file contents for recovery without following links.

        Args:
            path (Path): Native filesystem entry operated on by this method.

        Returns:
            bytes: Exact regular-file contents, without decoding or newline conversion.
        """
        ...

    def write_bytes(self, path: Path, contents: bytes, /) -> None:
        """Restore exact metadata bytes using protected file access.

        Args:
            path (Path): Native filesystem entry operated on by this method.
            contents (bytes): Complete file or JSON contents, using the annotated bytes/text type without implicit
                conversion.

        Returns:
            None: No return value.
        """
        ...

    def update_field(self, path: Path, field_name: str, new_value, /) -> None:
        """Update a raw JSON field without discarding unknown extension fields.

        Args:
            path (Path): Native filesystem entry operated on by this method.
            field_name (str): Metadata field or model label selected by this operation.
            new_value (object): New JSON-compatible value; the serializer's converter handles supported datetime/enum
                values.

        Returns:
            None: No return value.
        """
        ...


@dataclass
class SnapshotStorage:
    """Live model and storage paths for one invocation of a manager operation.

    Facades construct this context from their current public attributes on each
    call. Paths retain the manager's originally captured values, so changing an
    ID or JSON filename is detected instead of silently redirecting writes.
    Constructing this context performs no I/O and no extra model validation.

    Attributes:
        snapshot (Snapshot): Snapshot model used or mutated by this operation; association identities are retained
            where documented.
        settings (SnapshotSettings): Mutable snapshot settings retained by reference; no defensive copy is made.
        path_catalogue (Path): Catalogue root retained by this collaborator.
        path_snapshot (Path): Snapshot root captured by the manager/storage context.
        path_snapshot_json (Path): Metadata file path captured when the manager/storage context was constructed.
        metadata (SnapshotMetadata): Protected JSON/file-I/O adapter (SnapshotSerializer by default), retaining
            hook behavior for this operation.

    """

    snapshot: Snapshot
    settings: SnapshotSettings
    path_catalogue: Path
    path_snapshot: Path
    path_snapshot_json: Path

    # The class object provides bound class/static methods, as verified by the adapter tests.
    metadata: SnapshotMetadata = cast(SnapshotMetadata, SnapshotSerializer)

    def root_path(self) -> Path:
        """Revalidate the root and reject an ID changed after manager creation.

        Returns:
            Path: Validated captured root; mutating the model ID after manager creation is rejected.

        Raises:
            ValueError: A value, path, resource limit or metadata field violates the validation rules described above.
        """
        root = validate_snapshot_root(self.snapshot.folder_name, self.path_catalogue)
        if root != self.path_snapshot:
            raise ValueError("The snapshot ID changed after the manager was initialized.")
        return root

    def child_path(self, name: str) -> Path:
        """Validate the mutable model and resolve one direct stored child.

        Args:
            name (str): Attribute or filesystem-entry name inspected by this operation.

        Returns:
            Path: Validated direct child of the originally captured snapshot root.

        Raises:
            ValueError: A value, path, resource limit or metadata field violates the validation rules described above.
        """
        self.snapshot.validate()
        path = get_snapshot_child_path(self.snapshot.folder_name, self.path_catalogue, name)
        if path.parent != self.path_snapshot:
            raise ValueError("The snapshot ID changed after the manager was initialized.")
        return path

    def save_json(self) -> None:
        """Save only to the metadata path captured when the manager was created.

        Returns:
            None: No return value.

        Raises:
            ValueError: A value, path, resource limit or metadata field violates the validation rules described above.
        """
        json_path = self.child_path(self.settings.json_filename)
        if json_path != self.path_snapshot_json:
            raise ValueError("The snapshot JSON path changed after the manager was initialized.")
        self.metadata.to_json(self.snapshot, json_path)
