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
from pylizlib.core.data.text.models import TimedPattern
from pylizlib.core.data.text.preview import line_preview, needs_complete_line_preview
from pylizlib.core.data.text.results import ResultPage as _ResultPage
from pylizlib.core.data.text.search import TextFileSearcher
from pylizlib.core.log.pylizLogger import logger
from pylizlib.core.os.snap.callbacks import SnapshotProgressCallback
from pylizlib.core.os.snap.catalogue import SnapshotCatalogue
from pylizlib.core.os.snap.domain import Snapshot


class QueryType(Enum):
    """Select literal text or timed regular-expression matching.

    Attributes:
        TEXT (QueryType): Case-sensitive literal substring search.
        REGEX (QueryType): regex-engine matching with the configured per-call timeout.
    """

    TEXT = "text"
    REGEX = "regex"


class SearchTarget(Enum):
    """Select which part of each candidate file is searched.

    Attributes:
        FILE_NAME (SearchTarget): Match the basename without decoding file contents.
        FILE_CONTENT (SearchTarget): Decode content and retain at most one result per starting line.
    """

    FILE_NAME = "name"
    FILE_CONTENT = "content"


@dataclass
class SnapshotSearchResult:
    """Represents a single search result within a snapshot file.

    A content match is reported once per matching line. For a multiline match,
    ``line_number`` and ``line_content`` refer to the line where the match starts.

    Attributes:
        file_path (Path): Native file path associated with the match or current scan.
        searched_text (str): Query text or regex source at the time this result was recorded.
        snapshot_name (str): Snapshot display label copied into each public search result.
        line_number (Optional[int]): One-based starting line of a content match; None for filename-only results.
        line_content (Optional[str]): Stripped content-line preview, possibly with ellipses; None for filename-
            only results.
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
    ``max_line_preview_chars``. ``max_context_chars`` bounds retained regex context; it is not a strict
    maximum match length. Matches spanning beyond retained context are not
    guaranteed and can depend on chunk and EOF boundaries. ``encoding=None`` recognizes UTF-8 and UTF-16/32 BOMs, an ASCII-heavy
    bomless UTF-16 layout, UTF-8, then Windows-1252 fallback.

    Attributes:
        query (str): Query text or regex source; regex syntax is compiled at search time.
        search_target (SearchTarget): FILE_NAME for basename matching or FILE_CONTENT for decoded text.
        query_type (QueryType): TEXT for literal substring matching or REGEX for timed regex matching.
        extensions (list[str]): Case-insensitive suffix filters, with optional leading dots and compound suffixes;
            empty accepts all files.
        encoding (str | None): Explicit text codec, or None for the current BOM/UTF/Windows-1252 detection policy.
        max_files (int): Maximum candidate paths retained per snapshot, default 10000.
        max_results (int): Maximum retained page results, default 1000; zero produces an empty page.
        result_offset (int): Number of matching starting lines/names skipped across the complete search page.
        chunk_size (int): Decoded characters requested per stream read; default 65536, rather than a byte limit.
        max_context_chars (int): Retained regex-context budget in characters. It is not a hard maximum match
            length; spans beyond retained context are not guaranteed.
        max_line_preview_chars (int): Maximum preview characters before truncation ellipses, default 4096.
        regex_timeout_seconds (float): Timeout per regex call/window, default 0.1 seconds; not a global query
            deadline.
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
        """Reject invalid limits before any filesystem work begins.

        Returns:
            None: No return value.

        Raises:
            ValueError: A value, path, resource limit or metadata field violates the validation rules described above.
            LookupError: If an explicit encoding name is not a recognized codec.

        Notes:
            This validates numeric bounds and looks up an explicit codec. It does not compile query regex syntax or
            make the mutable configuration immutable; regex compilation happens when searching.
        """
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
        """Resolve a stored snapshot using the catalogue's current lookup policy.

        Args:
            snap (Snapshot): Snapshot model identifying the stored tree or operation target.

        Returns:
            Path | None: Validated stored directory when present, otherwise None; catalogue recovery may run before
                lookup.

        Notes:
            The catalogue implementation can invoke recovery while resolving the snapshot. Callers must not assume
            that this capability is filesystem-read-only.
        """
        ...


class SnapshotSearcher:
    """Search snapshot files with bounded memory, cancellation, and regex limits.

    Attributes:
        catalogue (SnapshotPathLookup): Catalogue capability used to resolve stored snapshot paths, including its
            recovery policy.
    """

    _DETECTION_SAMPLE_BYTES = 8 * 1024

    def __init__(self, catalogue: SnapshotCatalogue):
        """Initialize the searcher with the catalogue path lookup it needs.

        Args:
            catalogue (SnapshotCatalogue): Catalogue capability used to resolve stored snapshot paths, including its
                recovery policy.

        Returns:
            None: No return value.
        """
        self.catalogue: SnapshotPathLookup = catalogue

    def search(
        self,
        snapshot: Snapshot,
        params: SnapshotSearchParams,
        on_progress: Optional[SnapshotProgressCallback] = None,
    ) -> list[SnapshotSearchResult]:
        """Search one snapshot and return at most ``params.max_results`` matches.

        Args:
            snapshot (Snapshot): Snapshot model used or mutated by this operation; association identities are retained
                where documented.
            params (SnapshotSearchParams): Query, encoding and resource limits; the search observes this live
                configuration.
            on_progress (Optional[SnapshotProgressCallback]): Optional observer called with (filename, total_files,
                processed_files), also during chunks; only literal False cancels the current snapshot.

        Returns:
            list[SnapshotSearchResult]: At most max_results matches after result_offset, in existing traversal order.
                Content produces at most one result per starting line.

        Notes:
            A content result represents one starting line, including for multiline regexes. Offsets/results count
            those lines, not every occurrence. Only literal False from the observer cancels the current snapshot.
            Observer exceptions propagate unchanged; file read/decode errors are logged and skipped.
        """
        page = self._new_page(params)
        compiled_regex = self._compile_regex(params)
        if params.query_type == QueryType.REGEX and compiled_regex is None:
            return page.results

        snapshot_path = self.catalogue.get_snap_directory_path(snapshot)
        self._search_in_snapshot_path(snapshot, snapshot_path, params, compiled_regex, on_progress, page)
        logger.debug("Finished snapshot search snapshot=%s results=%s", snapshot.id, len(page.results))
        return page.results

    def search_list(
        self,
        snapshots: list[Snapshot],
        params: SnapshotSearchParams,
        on_progress: Optional[SnapshotProgressCallback] = None,
    ) -> list[SnapshotSearchResult]:
        """Search snapshots in order, applying one bounded page across all of them.

        Args:
            snapshots (list[Snapshot]): Snapshot models processed in supplied order; search pagination spans the whole
                list.
            params (SnapshotSearchParams): Query, encoding and resource limits; the search observes this live
                configuration.
            on_progress (Optional[SnapshotProgressCallback]): Optional observer called with (filename, total_files,
                processed_files), also during chunks; only literal False cancels the current snapshot.

        Returns:
            list[SnapshotSearchResult]: One bounded page shared across the supplied snapshot order; max_files and
                callback cancellation remain scoped to each snapshot.

        Notes:
            One offset/limit page spans all snapshots. max_files and literal-False cancellation apply to each current
            snapshot, so later snapshots may still be searched. Encoding retry discards the failed file attempt before
            committing results.
        """
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
        """Create a result page using the caller's pagination limits.

        Args:
            params (SnapshotSearchParams): Query, encoding and resource limits; the search observes this live
                configuration.

        Returns:
            _ResultPage: Empty bounded page initialized with the requested global offset and limit.
        """
        return _ResultPage(params.result_offset, params.max_results)

    @staticmethod
    def _compile_regex(params: SnapshotSearchParams) -> Optional[TimedPattern]:
        """Compile a regex query, logging invalid patterns without raising.

        Args:
            params (SnapshotSearchParams): Query, encoding and resource limits; the search observes this live
                configuration.

        Returns:
            Optional[TimedPattern]: Compiled regex for REGEX mode, otherwise None; invalid regex syntax is
                logged and also yields None.
        """
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
        compiled_regex: Optional[TimedPattern],
        on_progress: Optional[SnapshotProgressCallback],
        page: _ResultPage,
    ) -> None:
        """Search a resolved snapshot directory into an existing bounded page.

        Args:
            snapshot (Snapshot): Snapshot model used or mutated by this operation; association identities are retained
                where documented.
            snapshot_path (Path | None): Stored snapshot directory to validate or search.
            params (SnapshotSearchParams): Query, encoding and resource limits; the search observes this live
                configuration.
            compiled_regex (Optional[TimedPattern]): Compiled regex used when literal matching is disabled;
                None produces no regex matches.
            on_progress (Optional[SnapshotProgressCallback]): Optional observer called with (filename, total_files,
                processed_files), also during chunks; only literal False cancels the current snapshot.
            page (_ResultPage): Bounded result sink retaining remaining offset, limit and successful matches.

        Returns:
            None: No return value.
        """
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
        """Apply file and case-insensitive suffix filters, including compound suffixes.

        Args:
            file_path (Path): Native candidate file path to filter, inspect or search.
            extensions (list[str]): Suffix filters, case-insensitive, with optional leading dots and compound
                suffixes; empty searches all files.

        Returns:
            bool: Whether the entry is a file and matches any enabled case-insensitive suffix filter.
        """
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
        compiled_regex: Optional[TimedPattern],
        snapshot_name: str,
        page: _ResultPage,
        on_progress: Optional[SnapshotProgressCallback],
        total_files: int,
        processed_files: int,
    ) -> bool:
        """Scan a file in chunks; return True when the callback cancels the snapshot.

        Args:
            file_path (Path): Native candidate file path to filter, inspect or search.
            params (SnapshotSearchParams): Query, encoding and resource limits; the search observes this live
                configuration.
            compiled_regex (Optional[TimedPattern]): Compiled regex used when literal matching is disabled;
                None produces no regex matches.
            snapshot_name (str): Snapshot display label copied into each public search result.
            page (_ResultPage): Bounded result sink retaining remaining offset, limit and successful matches.
            on_progress (Optional[SnapshotProgressCallback]): Optional observer called with (filename, total_files,
                processed_files), also during chunks; only literal False cancels the current snapshot.
            total_files (int): Candidate-file count for the current snapshot, passed unchanged to search observers.
            processed_files (int): One-based index of the current candidate file, passed unchanged during its chunks.

        Returns:
            bool: True only when a chunk observer returns literal False; False for normal completion, skipped
                I/O/decoding or regex timeout.

        Notes:
            File I/O/decoding failures are logged and skipped. Observer exceptions propagate unchanged. A late UTF-8
            failure retries the whole file as Windows-1252 without retaining the first attempt's page.
        """
        from pylizlib.core.os.snap.searching import SnapshotMatchPage, SnapshotTextOptions

        on_chunk = None if on_progress is None else (lambda: on_progress(file_path.name, total_files, processed_files) if on_progress else None)
        return TextFileSearcher(self._DETECTION_SAMPLE_BYTES).search_file(file_path, SnapshotTextOptions(params), compiled_regex, SnapshotMatchPage(page, snapshot_name), on_chunk)

    def _detect_encoding(self, file_path: Path, preferred_encoding: str | None) -> tuple[str, bool, bool]:
        """Detect BOM, UTF-16 layout, UTF-8, or CP1252 and identify obvious binary data.

        Args:
            file_path (Path): Native candidate file path to filter, inspect or search.
            preferred_encoding (str | None): Explicit codec bypassing automatic classification, or None for
                BOM/UTF/Windows-1252 detection.

        Returns:
            tuple[str, bool, bool]: Codec name, binary classification and whether Windows-1252 fallback was selected,
                in that order.
        """
        decision = EncodingDetector(self._DETECTION_SAMPLE_BYTES).detect(file_path, preferred_encoding)
        return decision.encoding, decision.binary, decision.used_fallback

    @staticmethod
    def _detect_bomless_utf16(sample: bytes) -> str | None:
        """Recognize ASCII-heavy UTF-16 data from its alternating NUL bytes.

        Args:
            sample (bytes): Bounded raw byte sample used for encoding or binary detection.

        Returns:
            str | None: utf-16-le or utf-16-be for the existing alternating-NUL heuristic, otherwise None.
        """
        return EncodingDetector.detect_bomless_utf16(sample)

    @staticmethod
    def _looks_binary(sample: bytes, decoded: str, allow_nul: bool = False) -> bool:
        """Use conservative NUL/control-character checks for obvious binary files.

        Args:
            sample (bytes): Bounded raw byte sample used for encoding or binary detection.
            decoded (str): Sample text already decoded, with replacement characters where the detector permits them.
            allow_nul (bool): Allow raw NUL bytes for recognized UTF-16/32 samples when True.

        Returns:
            bool: Whether the sample contains a forbidden NUL or has a printable-character ratio below 0.65.
        """
        return EncodingDetector.looks_binary(sample, decoded, allow_nul)

    @staticmethod
    def _needs_complete_line_preview(
        buffer: str,
        match_start: int,
        max_chars: int,
        buffer_starts_mid_line: bool,
        final: bool,
    ) -> bool:
        """Wait for EOF or a newline before returning an untruncated short line.

        Args:
            buffer (str): Current decoded text window; offsets passed with it are relative to this string.
            match_start (int): Zero-based match start relative to the current text buffer.
            max_chars (int): Positive preview-width limit in decoded characters, before truncation ellipses.
            buffer_starts_mid_line (bool): Whether characters preceding the first retained line were discarded.
            final (bool): Whether this is the EOF scan, so matches and short trailing previews need no further chunk.

        Returns:
            bool: Whether a short unfinished line requires another chunk before its preview is complete.
        """
        return needs_complete_line_preview(buffer, match_start, max_chars, buffer_starts_mid_line, final)

    @staticmethod
    def _line_preview(
        buffer: str,
        match_start: int,
        max_chars: int,
        buffer_starts_mid_line: bool,
        final: bool,
    ) -> str:
        """Return a bounded preview of the line containing a match.

        Args:
            buffer (str): Current decoded text window; offsets passed with it are relative to this string.
            match_start (int): Zero-based match start relative to the current text buffer.
            max_chars (int): Positive preview-width limit in decoded characters, before truncation ellipses.
            buffer_starts_mid_line (bool): Whether characters preceding the first retained line were discarded.
            final (bool): Whether this is the EOF scan, so matches and short trailing previews need no further chunk.

        Returns:
            str: Stripped line preview with the configured character cap plus ellipses when either side was truncated.
        """
        return line_preview(buffer, match_start, max_chars, buffer_starts_mid_line, final)

    def _collect_files(
        self,
        snapshot: Snapshot,
        snapshot_path: Path,
        extensions: list[str],
        max_files: int,
    ) -> list[Path]:
        """Collect no more than the configured number of searchable file paths.

        Args:
            snapshot (Snapshot): Snapshot model used or mutated by this operation; association identities are retained
                where documented.
            snapshot_path (Path): Stored snapshot directory to validate or search.
            extensions (list[str]): Suffix filters, case-insensitive, with optional leading dots and compound
                suffixes; empty searches all files.
            max_files (int): Maximum candidate paths retained for one snapshot; later candidates are not visited after
                the limit.

        Returns:
            list[Path]: At most max_files matching paths, visited by association order then the native rglob
                traversal.
        """
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
        compiled_regex: Optional[TimedPattern],
    ) -> bool:
        """Match a filename using the same text and timed-regex rules as content.

        Args:
            text (str): Filename or text string to match using the selected literal/regex policy.
            params (SnapshotSearchParams): Query, encoding and resource limits; the search observes this live
                configuration.
            compiled_regex (Optional[TimedPattern]): Compiled regex used when literal matching is disabled;
                None produces no regex matches.

        Returns:
            bool: Whether literal substring or timed regex matching accepts the filename; regex timeouts return False.
        """
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
