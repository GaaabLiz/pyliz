"""Optional copy capabilities kept separate from the public strategy ABC."""

from collections.abc import Callable, Mapping, MutableMapping
from pathlib import Path
from typing import Protocol, runtime_checkable

from pylizlib.core.os.snap.callbacks import CopyProgressCallback, MessageCallback

MetadataCopier = Callable[[Path, Path], None]


@runtime_checkable
class MetadataCopyCapability(Protocol):
    """Opt into metadata copying while the delegate owns its stable source lifetime."""

    def copy_directory_with_metadata(
        self,
        source: Path,
        destination: Path,
        progress_callback: CopyProgressCallback | None = None,
        message_callback: MessageCallback | None = None,
        *,
        metadata_copier: MetadataCopier,
        manifest: MutableMapping[str, dict[str, str | int | None]] | None = None,
        expected_manifest: Mapping[str, dict[str, str | int | None]] | None = None,
    ) -> Path:
        """Copy content and apply metadata before releasing a stable source.

        Args:
            source (Path): Requested source tree.
            destination (Path): Absent destination published only on success.
            progress_callback (CopyProgressCallback | None): Byte progress observer.
            message_callback (MessageCallback | None): Per-file status observer.
            metadata_copier (MetadataCopier): Hook called with the actual stable
                source and completed staging tree while that source remains valid.
            manifest (MutableMapping | None): Receives captured integrity only on success.
            expected_manifest (Mapping | None): Expected content to verify before publishing.

        Returns:
            Path: Final destination after content and metadata complete.

        Raises:
            Exception: Copy, verification, metadata and observer failures propagate;
                implementations remove their partial destination.
        """
        ...
