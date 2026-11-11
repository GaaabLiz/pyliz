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
import io
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Protocol

import regex as regex_engine

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


@dataclass
class _ResultPage:
    """Collect one bounded result page while counting skipped matches."""

    offset_remaining: int
    limit: int
    results: list[SnapshotSearchResult] = field(default_factory=list)

    @property
    def full(self) -> bool:
        """Return whether this page has reached its configured result limit."""
        return len(self.results) >= self.limit

    def add(self, result: SnapshotSearchResult) -> None:
        """Skip earlier matches and retain only results that fit this page."""
        if self.offset_remaining:
            self.offset_remaining -= 1
        elif not self.full:
            self.results.append(result)

    def fork(self) -> _ResultPage:
        """Create a file-local page that can be discarded after a decode retry."""
        return _ResultPage(self.offset_remaining, self.limit - len(self.results))

    def commit(self, child: _ResultPage) -> None:
        """Add a completed file's page and skipped-match count to this page."""
        self.offset_remaining = child.offset_remaining
        self.results.extend(child.results)


class _ProgressCallbackError(Exception):
    """Carry an observer exception through file I/O handling unchanged."""

    def __init__(self, original: Exception):
        """Store the user exception that should be re-raised by the caller."""
        self.original = original


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
            logger.warning(
                f"Snapshot path '{snapshot_path}' for snapshot id '{snapshot.id}' does not exist or is not a directory."
            )
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
        try:
            encoding, binary, used_fallback = self._detect_encoding(file_path, params.encoding)
            if binary:
                logger.debug("Skipping file with binary content during search: %s", file_path)
                return False
            if used_fallback:
                logger.debug("UTF-8 decoding failed for text file %s; searching as Windows-1252", file_path)

            initial_page = page.fork()
            attempt_page = initial_page.fork()
            try:
                cancelled = self._scan_file(
                    file_path,
                    encoding,
                    params,
                    compiled_regex,
                    snapshot_name,
                    attempt_page,
                    on_progress,
                    total_files,
                    processed_files,
                )
            except UnicodeDecodeError:
                if params.encoding is None and encoding in {"utf-8", "utf-8-sig"}:
                    logger.warning(
                        "UTF-8 decoding failed while reading text file %s; retrying with Windows-1252",
                        file_path,
                    )
                    attempt_page = initial_page.fork()
                    cancelled = self._scan_file(
                        file_path,
                        "cp1252",
                        params,
                        compiled_regex,
                        snapshot_name,
                        attempt_page,
                        on_progress,
                        total_files,
                        processed_files,
                    )
                else:
                    logger.warning("Text decoding failed for %s using %s", file_path, encoding)
                    return False
            page.commit(attempt_page)
            return cancelled
        except _ProgressCallbackError as error:
            raise error.original
        except Exception as error:
            logger.warning("Error reading file %s during search: %s", file_path, error)
            return False

    def _detect_encoding(self, file_path: Path, preferred_encoding: str | None) -> tuple[str, bool, bool]:
        """Detect BOM, UTF-16 layout, UTF-8, or CP1252 and identify obvious binary data."""
        with file_path.open("rb") as file_stream:
            sample = file_stream.read(self._DETECTION_SAMPLE_BYTES)

        if preferred_encoding:
            return preferred_encoding, False, False
        if sample.startswith(codecs.BOM_UTF32_LE):
            encoding = "utf-32"
        elif sample.startswith(codecs.BOM_UTF32_BE):
            encoding = "utf-32"
        elif sample.startswith(codecs.BOM_UTF8):
            encoding = "utf-8-sig"
        elif sample.startswith(codecs.BOM_UTF16_LE) or sample.startswith(codecs.BOM_UTF16_BE):
            encoding = "utf-16"
        else:
            encoding = self._detect_bomless_utf16(sample) or ""
            if not encoding:
                try:
                    codecs.getincrementaldecoder("utf-8")().decode(
                        sample,
                        final=len(sample) < self._DETECTION_SAMPLE_BYTES,
                    )
                    encoding = "utf-8"
                except UnicodeDecodeError:
                    encoding = "cp1252"
                    text = sample.decode(encoding, errors="replace")
                    if self._looks_binary(sample, text):
                        return encoding, True, True
                    return encoding, False, True

        try:
            codecs.lookup(encoding)
        except LookupError:
            raise ValueError(f"Unknown text encoding: {encoding}")
        if self._looks_binary(
            sample,
            sample.decode(encoding, errors="replace"),
            allow_nul=encoding.startswith(("utf-16", "utf-32")),
        ):
            return encoding, True, False
        return encoding, False, False

    @staticmethod
    def _detect_bomless_utf16(sample: bytes) -> str | None:
        """Recognize ASCII-heavy UTF-16 data from its alternating NUL bytes."""
        pairs = len(sample) // 2
        if pairs < 4:
            return None
        even_nuls = sum(byte == 0 for byte in sample[: pairs * 2 : 2])
        odd_nuls = sum(byte == 0 for byte in sample[1 : pairs * 2 : 2])
        threshold = max(3, pairs // 4)
        if odd_nuls >= threshold and even_nuls <= pairs // 20:
            return "utf-16-le"
        if even_nuls >= threshold and odd_nuls <= pairs // 20:
            return "utf-16-be"
        return None

    @staticmethod
    def _looks_binary(sample: bytes, decoded: str, allow_nul: bool = False) -> bool:
        """Use conservative NUL/control-character checks for obvious binary files."""
        if not sample:
            return False
        if b"\x00" in sample and not allow_nul:
            return True
        if not decoded:
            return False
        printable = sum(character.isprintable() or character in "\r\n\t\f" for character in decoded)
        return printable / len(decoded) < 0.65

    def _scan_file(
        self,
        file_path: Path,
        encoding: str,
        params: SnapshotSearchParams,
        compiled_regex: Optional[regex_engine.Pattern],
        snapshot_name: str,
        page: _ResultPage,
        on_progress: Optional[SnapshotProgressCallback],
        total_files: int,
        processed_files: int,
    ) -> bool:
        """Read and search one text file without materializing its full contents."""
        errors = "strict" if encoding in {"utf-8", "utf-8-sig", "utf-16", "utf-16-le", "utf-16-be", "utf-32"} else "replace"
        with file_path.open("rb") as raw_stream:
            with io.TextIOWrapper(raw_stream, encoding=encoding, errors=errors, newline=None) as stream:
                query_window = len(params.query) if params.query_type == QueryType.TEXT else params.max_context_chars
                context_limit = max(params.max_context_chars, query_window)
                final_window_limit = context_limit
                if params.query_type == QueryType.TEXT:
                    final_window_limit = max(context_limit, params.max_line_preview_chars)
                buffer_limit = final_window_limit + params.chunk_size
                buffer = ""
                buffer_start = 0
                buffer_start_line = 1
                buffer_starts_mid_line = False
                scanned_until = 0
                total_chars = 0
                last_result_line: int | None = None

                while not page.full:
                    chunk = stream.read(params.chunk_size)
                    if not chunk:
                        break
                    if on_progress:
                        try:
                            keep_searching = on_progress(file_path.name, total_files, processed_files)
                        except Exception as error:
                            raise _ProgressCallbackError(error) from error
                        if keep_searching is False:
                            return True
                    buffer += chunk
                    total_chars += len(chunk)
                    if len(buffer) > buffer_limit:
                        dropped_count = len(buffer) - buffer_limit
                        dropped = buffer[:dropped_count]
                        buffer = buffer[dropped_count:]
                        buffer_start += dropped_count
                        buffer_start_line += dropped.count("\n")
                        buffer_starts_mid_line = not dropped.endswith("\n")

                    if params.query_type == QueryType.TEXT:
                        safe_until = total_chars - max(0, len(params.query) - 1)
                    else:
                        safe_until = total_chars - context_limit + 1
                    safe_until = max(scanned_until, safe_until)
                    last_result_line, deferred_match, regex_timed_out = self._search_buffer(
                        file_path,
                        buffer,
                        buffer_start,
                        buffer_start_line,
                        buffer_starts_mid_line,
                        max(0, max(scanned_until, buffer_start) - buffer_start),
                        max(0, safe_until - buffer_start),
                        params,
                        compiled_regex,
                        snapshot_name,
                        page,
                        last_result_line,
                        final=False,
                    )
                    if regex_timed_out:
                        return False
                    scanned_until = deferred_match if deferred_match is not None else safe_until

                if not page.full:
                    final_buffer = buffer
                    final_buffer_start = buffer_start
                    final_line_number = buffer_start_line
                    final_starts_mid_line = buffer_starts_mid_line
                    dropped_count = max(0, len(final_buffer) - final_window_limit)
                    if dropped_count:
                        dropped = final_buffer[:dropped_count]
                        final_buffer = final_buffer[dropped_count:]
                        final_buffer_start += dropped_count
                        final_line_number += dropped.count("\n")
                        final_starts_mid_line = not dropped.endswith("\n")
                    self._search_buffer(
                        file_path,
                        final_buffer,
                        final_buffer_start,
                        final_line_number,
                        final_starts_mid_line,
                        max(0, scanned_until - final_buffer_start),
                        len(final_buffer) + 1,
                        params,
                        compiled_regex,
                        snapshot_name,
                        page,
                        last_result_line,
                        final=True,
                    )
        return False

    def _search_buffer(
        self,
        file_path: Path,
        buffer: str,
        buffer_start: int,
        buffer_start_line: int,
        buffer_starts_mid_line: bool,
        scan_start: int,
        scan_until: int,
        params: SnapshotSearchParams,
        compiled_regex: Optional[regex_engine.Pattern],
        snapshot_name: str,
        page: _ResultPage,
        last_result_line: int | None,
        final: bool,
    ) -> tuple[int | None, int | None, bool]:
        """Search only uncommitted match starts in a rolling, bounded text window."""
        if not buffer or page.full or scan_start >= len(buffer) + 1:
            return last_result_line, None, False

        previous_match_start = 0
        current_line_number = buffer_start_line
        has_previous_match = False

        def add_match(start: int) -> tuple[int, bool]:
            """Add at most one result per line and return its line and novelty."""
            nonlocal current_line_number, has_previous_match, last_result_line, previous_match_start
            if has_previous_match:
                current_line_number += buffer[previous_match_start:start].count("\n")
            else:
                current_line_number += buffer[:start].count("\n")
                has_previous_match = True
            previous_match_start = start
            line_number = current_line_number
            is_new_line = line_number != last_result_line
            if is_new_line:
                line_content = self._line_preview(
                    buffer,
                    start,
                    params.max_line_preview_chars,
                    buffer_starts_mid_line,
                    final,
                )
                page.add(
                    SnapshotSearchResult(
                        file_path=file_path,
                        searched_text=params.query,
                        line_number=line_number,
                        line_content=line_content,
                        snapshot_name=snapshot_name,
                    )
                )
                last_result_line = line_number
            return line_number, is_new_line

        if params.query_type == QueryType.TEXT:
            position = scan_start
            while not page.full:
                match_start = buffer.find(params.query, position)
                if match_start < 0 or match_start >= scan_until:
                    break
                if self._needs_complete_line_preview(
                    buffer,
                    match_start,
                    params.max_line_preview_chars,
                    buffer_starts_mid_line,
                    final,
                ):
                    return last_result_line, buffer_start + match_start, False
                line_number, is_new_line = add_match(match_start)
                if not is_new_line:
                    next_line = buffer.find("\n", match_start)
                    if next_line < 0:
                        break
                    position = next_line + 1
                else:
                    position = match_start + 1
            return last_result_line, None, False

        if compiled_regex is None:
            return last_result_line, None, False
        try:
            matches = compiled_regex.finditer(
                buffer,
                pos=scan_start,
                timeout=params.regex_timeout_seconds,
            )
            for match in matches:
                if match.start() >= scan_until or page.full:
                    break
                if match.end() >= len(buffer) - 1 and not final:
                    return last_result_line, buffer_start + match.start(), False
                if self._needs_complete_line_preview(
                    buffer,
                    match.start(),
                    min(params.max_line_preview_chars, params.max_context_chars),
                    buffer_starts_mid_line,
                    final,
                ):
                    return last_result_line, buffer_start + match.start(), False
                add_match(match.start())
        except TimeoutError:
            logger.warning(
                "Regex search timed out for %s after %.3f seconds; remaining content in this file was skipped",
                file_path,
                params.regex_timeout_seconds,
            )
            return last_result_line, None, True
        return last_result_line, None, False

    @staticmethod
    def _needs_complete_line_preview(
        buffer: str,
        match_start: int,
        max_chars: int,
        buffer_starts_mid_line: bool,
        final: bool,
    ) -> bool:
        """Wait for EOF or a newline before returning an untruncated short line."""
        if final or buffer_starts_mid_line or buffer.find("\n", match_start) >= 0:
            return False
        line_start = buffer.rfind("\n", 0, match_start) + 1
        return len(buffer) - line_start <= max_chars

    @staticmethod
    def _line_preview(
        buffer: str,
        match_start: int,
        max_chars: int,
        buffer_starts_mid_line: bool,
        final: bool,
    ) -> str:
        """Return a bounded preview of the line containing a match."""
        line_start = buffer.rfind("\n", 0, match_start) + 1
        line_end = buffer.find("\n", match_start)
        right_truncated = line_end < 0 and not final
        if line_end < 0:
            line_end = len(buffer)
        line = buffer[line_start:line_end]
        left_truncated = line_start == 0 and buffer_starts_mid_line
        if len(line) <= max_chars and not left_truncated and not right_truncated:
            return line.strip()

        relative_match = max(0, match_start - line_start)
        start = max(0, relative_match - max_chars // 3)
        start = min(start, max(0, len(line) - max_chars))
        end = min(len(line), start + max_chars)
        preview = line[start:end]
        if left_truncated or start > 0:
            preview = "…" + preview
        if right_truncated or end < len(line):
            preview += "…"
        return preview.strip()

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
