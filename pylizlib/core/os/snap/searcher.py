"""
Full-text and filename search across snapshot contents.

Searches decode common text encodings, read content in bounded chunks, and keep
result pages bounded. Regex content searches are multiline and have a timeout
and a configurable maximum context window.

Classes:
    QueryType            – Enum: TEXT | REGEX.
    SearchTarget         – Enum: FILE_NAME | FILE_CONTENT.
    SnapshotSearchParams – Parameters for a search operation.
    SnapshotSearchResult – A single match found during a search.
    SnapshotSearcher     – Executes searches across snapshot directories.
"""

from __future__ import annotations

import codecs
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Protocol

import regex as regex_engine

from pylizlib.core.data.text.encoding import EncodingDetector
from pylizlib.core.data.text.preview import line_preview, needs_complete_line_preview
from pylizlib.core.data.text.results import ResultPage as _ResultPage
from pylizlib.core.data.text.search import TextFileSearcher
from pylizlib.core.log.pylizLogger import logger
from pylizlib.core.os.snap.callbacks import SnapshotProgressCallback
from pylizlib.core.os.snap.catalogue import SnapshotCatalogue
from pylizlib.core.os.snap.domain import Snapshot


class QueryType(Enum):
    """Specifies whether a search query is plain text or a regular expression."""

    TEXT = "text"
    REGEX = "regex"


class SearchTarget(Enum):
    """Specifies whether to search for a file name or within file content."""

    FILE_NAME = "name"
    FILE_CONTENT = "content"


@dataclass
class SnapshotSearchResult:
    """
    Represents a single search result within a snapshot file.

    A content match is reported once per matching line. For a multiline match,
    ``line_number`` and ``line_content`` refer to the line where the match starts.
    """

    file_path: Path
    searched_text: str
    snapshot_name: str
    line_number: Optional[int] = None
    line_content: Optional[str] = None


@dataclass
class SnapshotSearchParams:
    """Search query and resource limits for a search operation.

    ``max_results`` and ``result_offset`` provide a bounded result page;
    ``search_list`` applies that page across the full list of snapshots.
    ``max_files`` caps the candidate paths retained for a search. Content is
    read in ``chunk_size`` blocks, with each result's line preview capped by
    ``max_line_preview_chars``. Regex matches can span at most
    ``max_context_chars`` of content; longer spans are intentionally outside
    the bounded search window. ``encoding=None`` selects UTF-8, BOM-marked or
    detectable UTF-16, then Windows-1252 for text that is not valid UTF-8.
    """

    query: str
    search_target: SearchTarget = SearchTarget.FILE_CONTENT
    query_type: QueryType = QueryType.TEXT
    extensions: list[str] = field(default_factory=list)
    encoding: str | None = None
    max_files: int = 10_000
    max_results: int = 1_000
    result_offset: int = 0
    chunk_size: int = 64 * 1024
    max_context_chars: int = 1024 * 1024
    max_line_preview_chars: int = 4_096
    regex_timeout_seconds: float = 0.1

    def __post_init__(self) -> None:
        """Reject invalid limits before any filesystem work begins."""
        if self.max_files < 1:
            raise ValueError("max_files must be at least 1")
        if self.max_results < 0:
            raise ValueError("max_results cannot be negative")
        if self.result_offset < 0:
            raise ValueError("result_offset cannot be negative")
        if self.chunk_size < 1:
            raise ValueError("chunk_size must be at least 1")
        if self.max_context_chars < 1:
            raise ValueError("max_context_chars must be at least 1")
        if self.max_line_preview_chars < 1:
            raise ValueError("max_line_preview_chars must be at least 1")
        if self.regex_timeout_seconds <= 0:
            raise ValueError("regex_timeout_seconds must be greater than 0")
        if self.encoding is not None:
            codecs.lookup(self.encoding)


class SnapshotPathLookup(Protocol):
    """The only catalogue capability required by snapshot searching."""

    def get_snap_directory_path(self, snap: Snapshot) -> Path | None:
        """Resolve a stored snapshot using the catalogue's current lookup policy."""
        ...


class SnapshotSearcher:
    """Search snapshot files with bounded memory, cancellation, and regex limits."""

    _DETECTION_SAMPLE_BYTES = 8 * 1024

    def __init__(self, catalogue: SnapshotCatalogue):
        """Initialize the searcher with the catalogue path lookup it needs."""
        self.catalogue: SnapshotPathLookup = catalogue

    def search(
        self,
        snapshot: Snapshot,
        params: SnapshotSearchParams,
        on_progress: Optional[SnapshotProgressCallback] = None,
    ) -> list[SnapshotSearchResult]:
        """Search one snapshot and return at most ``params.max_results`` matches."""
        page = self._new_page(params)
        compiled_regex = self._compile_regex(params)
        if params.query_type == QueryType.REGEX and compiled_regex is None:
            return page.results

        snapshot_path = self.catalogue.get_snap_directory_path(snapshot)
        self._search_in_snapshot_path(snapshot, snapshot_path, params, compiled_regex, on_progress, page)
        return page.results

    def search_list(
        self,
        snapshots: list[Snapshot],
        params: SnapshotSearchParams,
        on_progress: Optional[SnapshotProgressCallback] = None,
    ) -> list[SnapshotSearchResult]:
        """Search snapshots in order, applying one bounded page across all of them."""
        page = self._new_page(params)
        compiled_regex = self._compile_regex(params)
        if params.query_type == QueryType.REGEX and compiled_regex is None:
            return page.results

        for snapshot in snapshots:
            if page.full:
                break
            snapshot_path = self.catalogue.get_snap_directory_path(snapshot)
            self._search_in_snapshot_path(snapshot, snapshot_path, params, compiled_regex, on_progress, page)
        return page.results

    @staticmethod
    def _new_page(params: SnapshotSearchParams) -> _ResultPage:
        """Create a result page using the caller's pagination limits."""
        return _ResultPage(params.result_offset, params.max_results)

    @staticmethod
    def _compile_regex(params: SnapshotSearchParams) -> Optional[regex_engine.Pattern]:
        """Compile a regex query, logging invalid patterns without raising."""
        if params.query_type != QueryType.REGEX:
            return None
        try:
            return regex_engine.compile(params.query)
        except regex_engine.error as error:
            logger.error(f"Invalid regex pattern provided: {error}")
            return None

    def _search_in_snapshot_path(
        self,
        snapshot: Snapshot,
        snapshot_path: Path | None,
        params: SnapshotSearchParams,
        compiled_regex: Optional[regex_engine.Pattern],
        on_progress: Optional[SnapshotProgressCallback],
        page: _ResultPage,
    ) -> None:
        """Search a resolved snapshot directory into an existing bounded page."""
        if page.full:
            return
        if not snapshot_path or not snapshot_path.is_dir():
            logger.warning(f"Snapshot path '{snapshot_path}' for snapshot id '{snapshot.id}' does not exist or is not a directory.")
            return

        files_to_search = self._collect_files(snapshot, snapshot_path, params.extensions, params.max_files)
        total_files = len(files_to_search)
        for index, file_path in enumerate(files_to_search, 1):
            if page.full:
                break
            if on_progress and on_progress(file_path.name, total_files, index) is False:
                break

            if params.search_target == SearchTarget.FILE_NAME:
                if self._matches(file_path.name, params, compiled_regex):
                    page.add(
                        SnapshotSearchResult(
                            file_path=file_path,
                            searched_text=params.query,
                            snapshot_name=snapshot.name,
                        )
                    )
            elif params.search_target == SearchTarget.FILE_CONTENT:
                file_page = page.fork()
                cancelled = self._search_in_file(
                    file_path,
                    params,
                    compiled_regex,
                    snapshot.name,
                    file_page,
                    on_progress,
                    total_files,
                    index,
                )
                page.commit(file_page)
                if cancelled:
                    break

        if len(files_to_search) == params.max_files:
            logger.warning(
                "Search reached max_files=%d for snapshot %s; additional files may not have been searched.",
                params.max_files,
                snapshot.id,
            )

    def _should_search_file(self, file_path: Path, extensions: list[str]) -> bool:
        """Apply file and case-insensitive suffix filters, including compound suffixes."""
        if not file_path.is_file():
            return False
        if not extensions:
            return True
        normalized = [extension.casefold() if extension.startswith(".") else f".{extension.casefold()}" for extension in extensions]
        name = file_path.name.casefold()
        return any(name.endswith(extension) for extension in normalized if extension != ".")

    def _search_in_file(
        self,
        file_path: Path,
        params: SnapshotSearchParams,
        compiled_regex: Optional[regex_engine.Pattern],
        snapshot_name: str,
        page: _ResultPage,
        on_progress: Optional[SnapshotProgressCallback],
        total_files: int,
        processed_files: int,
    ) -> bool:
        """Scan a file in chunks; return True when the callback cancels the snapshot."""
        from pylizlib.core.os.snap.searching import SnapshotMatchPage, SnapshotTextOptions

        on_chunk = (lambda: on_progress(file_path.name, total_files, processed_files)) if on_progress else None
        return TextFileSearcher(self._DETECTION_SAMPLE_BYTES).search_file(file_path, SnapshotTextOptions(params), compiled_regex, SnapshotMatchPage(page, snapshot_name), on_chunk)

    def _detect_encoding(self, file_path: Path, preferred_encoding: str | None) -> tuple[str, bool, bool]:
        """Detect BOM, UTF-16 layout, UTF-8, or CP1252 and identify obvious binary data."""
        decision = EncodingDetector(self._DETECTION_SAMPLE_BYTES).detect(file_path, preferred_encoding)
        return decision.encoding, decision.binary, decision.used_fallback

    @staticmethod
    def _detect_bomless_utf16(sample: bytes) -> str | None:
        """Recognize ASCII-heavy UTF-16 data from its alternating NUL bytes."""
        return EncodingDetector.detect_bomless_utf16(sample)

    @staticmethod
    def _looks_binary(sample: bytes, decoded: str, allow_nul: bool = False) -> bool:
        """Use conservative NUL/control-character checks for obvious binary files."""
        return EncodingDetector.looks_binary(sample, decoded, allow_nul)

    @staticmethod
    def _needs_complete_line_preview(
        buffer: str,
        match_start: int,
        max_chars: int,
        buffer_starts_mid_line: bool,
        final: bool,
    ) -> bool:
        """Wait for EOF or a newline before returning an untruncated short line."""
        return needs_complete_line_preview(buffer, match_start, max_chars, buffer_starts_mid_line, final)

    @staticmethod
    def _line_preview(
        buffer: str,
        match_start: int,
        max_chars: int,
        buffer_starts_mid_line: bool,
        final: bool,
    ) -> str:
        """Return a bounded preview of the line containing a match."""
        return line_preview(buffer, match_start, max_chars, buffer_starts_mid_line, final)

    def _collect_files(
        self,
        snapshot: Snapshot,
        snapshot_path: Path,
        extensions: list[str],
        max_files: int,
    ) -> list[Path]:
        """Collect no more than the configured number of searchable file paths."""
        files_to_search: list[Path] = []
        for dir_assoc in snapshot.directories:
            copied_dir_path = snapshot_path.joinpath(dir_assoc.directory_name)
            if not copied_dir_path.is_dir():
                continue
            for file_path in copied_dir_path.rglob("*"):
                if self._should_search_file(file_path, extensions):
                    files_to_search.append(file_path)
                    if len(files_to_search) >= max_files:
                        return files_to_search
        return files_to_search

    @staticmethod
    def _matches(
        text: str,
        params: SnapshotSearchParams,
        compiled_regex: Optional[regex_engine.Pattern],
    ) -> bool:
        """Match a filename using the same text and timed-regex rules as content."""
        if params.query_type == QueryType.TEXT:
            return params.query in text
        if compiled_regex is None:
            return False
        try:
            return bool(compiled_regex.search(text, timeout=params.regex_timeout_seconds))
        except TimeoutError:
            logger.warning(
                "Regex search timed out while checking a filename after %.3f seconds",
                params.regex_timeout_seconds,
            )
            return False
