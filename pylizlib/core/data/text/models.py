"""Configuration and match contracts shared by text readers and matchers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class TextSearchConfiguration(Protocol):
    """Provide live query and limits, allowing adapters to retain mutable settings.

    Attributes:
        query (str): Literal text or compiled-regex source.
        literal (bool): True for literal matching, False for the supplied regex.
        encoding (str | None): Explicit codec, or None for automatic detection.
        chunk_size (int): Decoded characters requested per stream read, rather than a raw-byte limit.
        max_context_chars (int): Maximum context retained for regex windows.
        max_line_preview_chars (int): Preview character limit before ellipses.
        regex_timeout_seconds (float): Timeout supplied by the implementation for each regex call/window,
            rather than a global query deadline.
    """

    query: str
    literal: bool
    encoding: str | None
    chunk_size: int
    max_context_chars: int
    max_line_preview_chars: int
    regex_timeout_seconds: float


@dataclass
class TextSearchOptions:
    """Configure general streaming text search; callers supply positive limits.

    Attributes:
        query (str): Text to find, or the source of the supplied compiled regex.
        literal (bool): Select literal matching when True; regex otherwise.
        encoding (str | None): Explicit codec or None for BOM/UTF/Windows-1252 detection.
        chunk_size (int): Decoded characters requested per stream read; default 65536, rather than a byte limit.
        max_context_chars (int): Regex context bound, default 1048576 characters.
        max_line_preview_chars (int): Preview width before ellipses, default 4096.
        regex_timeout_seconds (float): Timeout per regex call/window, default 0.1 seconds; not a global query
            deadline.
    """

    query: str
    literal: bool = True
    encoding: str | None = None
    chunk_size: int = 64 * 1024
    max_context_chars: int = 1024 * 1024
    max_line_preview_chars: int = 4096
    regex_timeout_seconds: float = 0.1


@dataclass
class TextMatch:
    """Describe one matching starting line without application-specific metadata.

    Attributes:
        file_path (Path): Native path that was read.
        query (str): Query value when this match was retained.
        line_number (int): One-based starting line, after universal-newline decoding.
        line_content (str): Bounded, stripped line preview, possibly with ellipses.
    """

    file_path: Path
    query: str
    line_number: int
    line_content: str


class MatchPage(Protocol):
    """Accept matches in a bounded page with discardable per-file retry attempts."""

    @property
    def full(self) -> bool:
        """Return bool: whether this page has reached its result limit.

        Returns:
            bool: Whether this bounded page has reached its configured result limit.
        """
        ...

    def add(self, result: TextMatch) -> None:
        """Consume a TextMatch, respecting offset/limit; return None.

        Args:
            result (TextMatch): Match or value to consume according to this bounded page's offset/limit.

        Returns:
            None: No return value.
        """
        ...

    def fork(self) -> MatchPage:
        """Return MatchPage: an isolated attempt with the remaining offset/limit.

        Returns:
            MatchPage: Independent attempt with the remaining offset and capacity; its results can be discarded
                without mutating the parent.
        """
        ...

    def commit(self, child: MatchPage) -> None:
        """Merge a completed child MatchPage into this page; return None.

        Args:
            child (MatchPage): Successful isolated result-page attempt whose matches and consumed offset are
                committed.

        Returns:
            None: No return value.
        """
        ...


class _ProgressCallbackError(Exception):
    """Carry an observer exception unchanged through file-error handling.

    Attributes:
        original (Exception): Original observer exception, retained unchanged for re-raising outside file-error
            handling.
    """

    def __init__(self, original: Exception):
        """Retain the original Exception to be re-raised without file-error masking.

        Args:
            original (Exception): Original observer exception, retained unchanged for re-raising outside file-error
                handling.

        Returns:
            None: No return value.
        """
        self.original = original
