"""Bounded file reading, decode retries and per-attempt streaming sessions."""

from __future__ import annotations

import io
from collections.abc import Callable
from pathlib import Path

import regex as regex_engine

from pylizlib.core.data.text.encoding import EncodingDetector
from pylizlib.core.data.text.matching import BufferMatcher
from pylizlib.core.data.text.models import MatchPage, TextSearchConfiguration, _ProgressCallbackError
from pylizlib.core.data.text.models import TextMatch as TextMatch
from pylizlib.core.data.text.models import TextSearchOptions as TextSearchOptions
from pylizlib.core.data.text.window import TextWindow
from pylizlib.core.log.pylizLogger import logger


class TextFileSearcher:
    """Read files in bounded windows, preserving retry, line and timeout semantics."""

    def __init__(self, sample_bytes: int = 8192):
        """Set the maximum encoding-detection sample size in bytes.

        Args:
            sample_bytes (int): Maximum raw bytes read for encoding detection, default 8192.

        Returns:
            None: No return value.
        """
        self._DETECTION_SAMPLE_BYTES = sample_bytes

    def _detect_encoding(self, file_path: Path, preferred_encoding: str | None) -> tuple[str, bool, bool]:
        """Adapt the named encoding decision for the existing scan control flow.

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

    def search_file(
        self,
        file_path: Path,
        params: TextSearchConfiguration,
        compiled_regex: regex_engine.Pattern | None,
        page: MatchPage,
        on_chunk: Callable[[], bool | None] | None,
    ) -> bool:
        """Scan a file in chunks; return True when the callback cancels the snapshot.

        Args:
            file_path (Path): Native candidate file path to filter, inspect or search.
            params (TextSearchConfiguration): Query, encoding and resource limits; the search observes this live
                configuration.
            compiled_regex (regex_engine.Pattern | None): Compiled regex used when literal matching is disabled; None
                produces no regex matches.
            page (MatchPage): Bounded result sink retaining remaining offset, limit and successful matches.
            on_chunk (Callable[[], bool | None] | None): Optional zero-argument chunk observer; only literal False
                cancels, and observer exceptions propagate unchanged.

        Returns:
            bool: True only for literal-False observer cancellation. I/O/decoding failures are logged and skipped;
                observer exceptions propagate unchanged.

        Notes:
            Regex timeouts stop the remaining current-file scan and are logged. A late automatic UTF-8 failure retries
            as Windows-1252 with an isolated result page. Explicit codec failures do not enable that retry. Observer
            exceptions escape unchanged.
        """
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
        self, file_path: Path, encoding: str, params: TextSearchConfiguration, compiled_regex: regex_engine.Pattern | None, page: MatchPage, on_chunk: Callable[[], bool | None] | None
    ) -> bool:
        """Run one independent decode attempt; return whether the observer cancels.

        Args:
            file_path (Path): Native candidate file path to filter, inspect or search.
            encoding (str): Codec selected for this decode attempt; UTF encodings are strict and other codecs use
                replacement.
            params (TextSearchConfiguration): Query, encoding and resource limits; the search observes this live
                configuration.
            compiled_regex (regex_engine.Pattern | None): Compiled regex used when literal matching is disabled; None
                produces no regex matches.
            page (MatchPage): Bounded result sink retaining remaining offset, limit and successful matches.
            on_chunk (Callable[[], bool | None] | None): Optional zero-argument chunk observer; only literal False
                cancels, and observer exceptions propagate unchanged.

        Returns:
            bool: Whether this independent decode attempt was cancelled by its observer.
        """
        return TextScanSession(file_path, params, compiled_regex, page, on_chunk).scan(encoding)


class TextScanSession:
    """Own all mutable state for one decode attempt, never shared across retries.

    Attributes:
        file_path (Path): Native file path associated with the match or current scan.
        params (TextSearchConfiguration): Query, encoding and resource limits; the search observes this live
            configuration.
        page (MatchPage): Bounded result sink retaining remaining offset, limit and successful matches.
        on_chunk (Callable[[], bool | None] | None): Optional zero-argument chunk observer; only literal False
            cancels, and observer exceptions propagate unchanged.
        matcher (BufferMatcher): File-scoped matcher sharing live options and this attempt's result sink.
        context_limit (int): Context budget fixed at the start of this decode attempt.
        final_window_limit (int): EOF tail budget fixed from context/query/preview limits at attempt start.
        buffer_limit (int): Retained context/preview budget plus one decoded chunk.
        window (TextWindow): Retained text and its absolute character/line coordinates.
        scanned_until (int): Absolute character boundary whose match starts are already committed or deferred.
        total_chars (int): Total decoded characters read by this attempt, including discarded window prefixes.
        last_result_line (int | None): Last reported one-based starting line, or None before a retained match.
    """

    def __init__(self, file_path: Path, params: TextSearchConfiguration, compiled_regex: regex_engine.Pattern | None, page: MatchPage, on_chunk: Callable[[], bool | None] | None):
        """Retain one attempt's reader, query, sink and optional chunk observer.

        Args:
            file_path (Path): Native candidate file path to filter, inspect or search.
            params (TextSearchConfiguration): Query, encoding and resource limits; the search observes this live
                configuration.
            compiled_regex (regex_engine.Pattern | None): Compiled regex used when literal matching is disabled; None
                produces no regex matches.
            page (MatchPage): Bounded result sink retaining remaining offset, limit and successful matches.
            on_chunk (Callable[[], bool | None] | None): Optional zero-argument chunk observer; only literal False
                cancels, and observer exceptions propagate unchanged.

        Returns:
            None: No return value.
        """
        self.file_path = file_path
        self.params = params
        self.page = page
        self.on_chunk = on_chunk
        self.matcher = BufferMatcher(file_path, params, compiled_regex, page)

    def scan(self, encoding: str) -> bool:
        """Read and match bounded chunks, returning True only for explicit cancellation.

        Args:
            encoding (str): Codec selected for this decode attempt; UTF encodings are strict and other codecs use
                replacement.

        Returns:
            bool: True only for explicit observer cancellation; EOF, a full page or regex timeout produce False.
        """
        errors = "strict" if encoding in {"utf-8", "utf-8-sig", "utf-16", "utf-16-le", "utf-16-be", "utf-32"} else "replace"

        # Freeze window budgets for this attempt, retaining live query reads.
        with self.file_path.open("rb") as raw_stream:
            with io.TextIOWrapper(raw_stream, encoding=encoding, errors=errors, newline=None) as stream:
                self._initialize_window()
                while not self.page.full:
                    chunk = stream.read(self.params.chunk_size)
                    if not chunk:
                        break
                    if self._cancelled_by_observer():
                        return True

                    # Absolute offsets survive trimming of the retained text suffix.
                    self.window.append(chunk, self.buffer_limit)
                    self.total_chars += len(chunk)
                    if self._consume_window():
                        return False

                # EOF uses its own tail limit and does not alter the rolling window.
                if not self.page.full:
                    self._consume_final_window()
        return False

    def _initialize_window(self) -> None:
        """Initialize the original per-attempt budgets and named character counters.

        Returns:
            None: No return value.
        """
        query_window = len(self.params.query) if self.params.literal else self.params.max_context_chars
        self.context_limit = max(self.params.max_context_chars, query_window)
        self.final_window_limit = self.context_limit
        if self.params.literal:
            self.final_window_limit = max(self.context_limit, self.params.max_line_preview_chars)
        self.buffer_limit = self.final_window_limit + self.params.chunk_size
        self.window = TextWindow()
        self.scanned_until = 0
        self.total_chars = 0
        self.last_result_line: int | None = None

    def _cancelled_by_observer(self) -> bool:
        """Keep observer exceptions distinct from errors opening or decoding files.

        Returns:
            bool: Whether the observer returned literal False; exceptions are wrapped for the file-level handler to
                unwrap.

        Raises:
            _ProgressCallbackError: The observer raised; the file-level handler re-raises its original exception
                unchanged.
        """
        if self.on_chunk:
            try:
                keep_searching = self.on_chunk()
            except Exception as error:
                raise _ProgressCallbackError(error) from error
            return keep_searching is False
        return False

    def _consume_window(self) -> bool:
        """Commit safe match starts and return whether regex matching timed out.

        Returns:
            bool: True if regex matching timed out, otherwise False after updating committed/deferred coordinates.
        """
        if self.params.literal:
            safe_until = self.total_chars - max(0, len(self.params.query) - 1)
        else:
            safe_until = self.total_chars - self.context_limit + 1
        safe_until = max(self.scanned_until, safe_until)
        scan_start = max(0, max(self.scanned_until, self.window.start_offset) - self.window.start_offset)
        result = self.matcher.search(self.window, scan_start, max(0, safe_until - self.window.start_offset), self.last_result_line, final=False)
        self.last_result_line = result.last_result_line
        if result.regex_timed_out:
            return True
        self.scanned_until = result.deferred_match if result.deferred_match is not None else safe_until
        return False

    def _consume_final_window(self) -> None:
        """Search the bounded EOF tail without waiting for additional preview text.

        Returns:
            None: No return value.
        """
        final_window = self.window.tail(self.final_window_limit)
        self.matcher.search(final_window, max(0, self.scanned_until - final_window.start_offset), len(final_window.text) + 1, self.last_result_line, final=True)
