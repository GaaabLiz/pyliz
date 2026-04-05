from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class ResolvedMediaSource:
    """
    Represents a resolved media input, either coming from a filesystem path or a temporary file created from base64.
    """

    path: Path
    base64_content: str | None = None
    is_temporary: bool = False

