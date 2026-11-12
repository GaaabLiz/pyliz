"""Bounded file-content search with no dependency on snapshot models or layout."""

from __future__ import annotations

import io
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import regex as regex_engine

from pylizlib.core.data.text.encoding import EncodingDetector
from pylizlib.core.data.text.preview import line_preview, needs_complete_line_preview
from pylizlib.core.log.pylizLogger import logger


class TextSearchConfiguration(Protocol):
    """Provide live query and limits, allowing adapters to retain mutable settings.

    Attributes:
        query (str): Literal text or compiled-regex source.
        literal (bool): True for literal matching, False for the supplied regex.
        encoding (str | None): Explicit codec, or None for automatic detection.
        chunk_size (int): Characters read from the decoded stream per iteration.
        max_context_chars (int): Maximum context retained for regex windows.
        max_line_preview_chars (int): Preview character limit before ellipses.
        regex_timeout_seconds (float): Timeout per regex matching operation.
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
        chunk_size (int): Decoded characters per read, default 65536.
        max_context_chars (int): Regex context bound, default 1048576 characters.
        max_line_preview_chars (int): Preview width before ellipses, default 4096.
        regex_timeout_seconds (float): Timeout of each regex operation, default 0.1.
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
        """Return bool: whether this page has reached its result limit."""
        ...

    def add(self, result: TextMatch) -> None:
        """Consume a TextMatch, respecting offset/limit; return None."""
        ...

    def fork(self) -> MatchPage:
        """Return MatchPage: an isolated attempt with the remaining offset/limit."""
        ...

    def commit(self, child: MatchPage) -> None:
        """Merge a completed child MatchPage into this page; return None."""
        ...


class _ProgressCallbackError(Exception):
    """Carry an observer exception unchanged through file-error handling."""

    def __init__(self, original: Exception):
        """Retain the original Exception to be re-raised without file-error masking."""
        self.original = original


class TextFileSearcher:
    """Read files in bounded windows, preserving retry, line and timeout semantics."""

    def __init__(self, sample_bytes: int = 8192):
        """Set the maximum encoding-detection sample size in bytes."""
        self._DETECTION_SAMPLE_BYTES = sample_bytes

    def _detect_encoding(self, file_path: Path, preferred_encoding: str | None) -> tuple[str, bool, bool]:
        """Adapt the named encoding decision for the existing scan control flow."""
        decision = EncodingDetector(self._DETECTION_SAMPLE_BYTES).detect(file_path, preferred_encoding)
        return decision.encoding, decision.binary, decision.used_fallback

    def search_file(
        self,
        file_path: Path,
        params: TextSearchConfiguration,
        compiled_regex: regex_engine.Pattern | None,
        page: MatchPage,
        on_chunk: Callable[[], bool | None] | None,
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
                    attempt_page,
                    on_chunk,
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
                        attempt_page,
                        on_chunk,
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

    def _scan_file(
        self,
        file_path: Path,
        encoding: str,
        params: TextSearchConfiguration,
        compiled_regex: regex_engine.Pattern | None,
        page: MatchPage,
        on_chunk: Callable[[], bool | None] | None,
    ) -> bool:
        """Read and search one text file without materializing its full contents."""
        errors = "strict" if encoding in {"utf-8", "utf-8-sig", "utf-16", "utf-16-le", "utf-16-be", "utf-32"} else "replace"
        with file_path.open("rb") as raw_stream:
            with io.TextIOWrapper(raw_stream, encoding=encoding, errors=errors, newline=None) as stream:
                query_window = len(params.query) if params.literal else params.max_context_chars
                context_limit = max(params.max_context_chars, query_window)
                final_window_limit = context_limit
                if params.literal:
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
                    if on_chunk:
                        try:
                            keep_searching = on_chunk()
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

                    if params.literal:
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
        params: TextSearchConfiguration,
        compiled_regex: regex_engine.Pattern | None,
        page: MatchPage,
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
                line_content = line_preview(
                    buffer,
                    start,
                    params.max_line_preview_chars,
                    buffer_starts_mid_line,
                    final,
                )
                page.add(
                    TextMatch(
                        file_path=file_path,
                        query=params.query,
                        line_number=line_number,
                        line_content=line_content,
                    )
                )
                last_result_line = line_number
            return line_number, is_new_line

        if params.literal:
            position = scan_start
            while not page.full:
                match_start = buffer.find(params.query, position)
                if match_start < 0 or match_start >= scan_until:
                    break
                if needs_complete_line_preview(
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
                if needs_complete_line_preview(
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
