from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class ResolvedMediaSource:
    """
    Data container for a resolved media source.
    Encapsulates the final filesystem path and metadata about its origin.

    Attributes:
        path: The physical path to the media file on disk.
        base64_content: Original base64 or Data URI if source was not a local file.
        is_temporary: True if the file was created in a temp directory and should be cleaned up.
    """

    path: Path
    base64_content: str | None = None
    is_temporary: bool = False
