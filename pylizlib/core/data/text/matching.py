"""Match literal text or timed regexes inside one bounded decoded window."""

from __future__ import annotations

from pathlib import Path

from pylizlib.core.data.text.models import MatchPage, TextMatch, TextSearchConfiguration, TimedPattern
from pylizlib.core.data.text.preview import line_preview, needs_complete_line_preview
from pylizlib.core.data.text.window import BufferScanOutcome, TextWindow
from pylizlib.core.log.pylizLogger import logger


class _LineMatchCollector:
    """Maintain per-window line coordinates and at most one result per starting line.

    Attributes:
        matcher (BufferMatcher): File-scoped matcher sharing live options and this attempt's result sink.
        window (TextWindow): Retained text and its absolute character/line coordinates.
        last_result_line (int | None): Last reported one-based starting line, or None before a retained match.
        final (bool): Whether this is the EOF scan, so matches and short trailing previews need no further chunk.
        previous_match_start (int): Previous buffer-relative match start used for line increments.
        current_line_number (int): One-based line currently tracked by the window collector.
        has_previous_match (bool): Whether the collector can increment from a previous start instead of recounting
            the window prefix.
    """

    def __init__(self, matcher: BufferMatcher, window: TextWindow, last_result_line: int | None, final: bool):
        """Bind the immutable scan inputs and initialize incremental line counting.

        Args:
            matcher (BufferMatcher): File-scoped matcher sharing live query options, compiled regex and result page.
            window (TextWindow): Retained text and its absolute character/line coordinates.
            last_result_line (int | None): Last reported one-based starting line, or None before the first retained
                match.
            final (bool): Whether this is the EOF scan, so matches and short trailing previews need no further chunk.

        Returns:
            None: No return value.
        """
        self.matcher = matcher
        self.window = window
        self.last_result_line = last_result_line
        self.final = final
        self.previous_match_start = 0
        self.current_line_number = window.start_line
        self.has_previous_match = False

    def add(self, start: int) -> bool:
        """Retain a match only if its starting line has not already been reported.

        Args:
            start (int): Zero-based match start relative to the current retained window.

        Returns:
            bool: True if this start belongs to a new reported line, False when that starting line was already
                reported.
        """
        text = self.window.text
        if self.has_previous_match:
            self.current_line_number += text[self.previous_match_start : start].count("\n")
        else:
            self.current_line_number += text[:start].count("\n")
            self.has_previous_match = True
        self.previous_match_start = start
        line_number = self.current_line_number
        is_new_line = line_number != self.last_result_line
        if is_new_line:
            params = self.matcher.params
            preview = line_preview(text, start, params.max_line_preview_chars, self.window.starts_mid_line, self.final)
            self.matcher.page.add(TextMatch(self.matcher.file_path, params.query, line_number, preview))
            self.last_result_line = line_number
        return is_new_line

    def outcome(self, deferred_match: int | None = None, *, regex_timed_out: bool = False) -> BufferScanOutcome:
        """Return the named line/delay/timeout outcome for this scan.

        Args:
            deferred_match (int | None): Absolute start to reconsider after reading another chunk, or None when
                nothing is pending.
            regex_timed_out (bool): Whether regex matching exhausted its per-operation timeout and the file scan
                should stop.

        Returns:
            BufferScanOutcome: Named last-line, deferred absolute start and timeout state for the current window.
        """
        return BufferScanOutcome(self.last_result_line, deferred_match, regex_timed_out)


class BufferMatcher:
    """Separate literal and regex algorithms from stream/window ownership.

    Attributes:
        file_path (Path): Native file path associated with the match or current scan.
        params (TextSearchConfiguration): Query, encoding and resource limits; the search observes this live
            configuration.
        compiled_regex (TimedPattern | None): Compiled regex used when literal matching is disabled; None
            produces no regex matches.
        page (MatchPage): Bounded result sink retaining remaining offset, limit and successful matches.
    """

    def __init__(self, file_path: Path, params: TextSearchConfiguration, compiled_regex: TimedPattern | None, page: MatchPage):
        """Bind live query options and the result sink for one file attempt.

        Args:
            file_path (Path): Native candidate file path to filter, inspect or search.
            params (TextSearchConfiguration): Query, encoding and resource limits; the search observes this live
                configuration.
            compiled_regex (TimedPattern | None): Compiled regex used when literal matching is disabled; None
                produces no regex matches.
            page (MatchPage): Bounded result sink retaining remaining offset, limit and successful matches.

        Returns:
            None: No return value.
        """
        self.file_path = file_path
        self.params = params
        self.compiled_regex = compiled_regex
        self.page = page

    def search(self, window: TextWindow, scan_start: int, scan_until: int, last_result_line: int | None, *, final: bool) -> BufferScanOutcome:
        """Search uncommitted starts in a window, returning named continuation state.

        Args:
            window (TextWindow): Retained text and its absolute character/line coordinates.
            scan_start (int): First eligible match-start offset relative to the retained text window.
            scan_until (int): Exclusive match-start boundary relative to the retained window; final scans may use
                len(text) + 1.
            last_result_line (int | None): Last reported one-based starting line, or None before the first retained
                match.
            final (bool): Whether this is the EOF scan, so matches and short trailing previews need no further chunk.

        Returns:
            BufferScanOutcome: Named last-result line, deferred absolute start and regex-timeout outcome for this
                retained window.
        """
        if not window.text or self.page.full or scan_start >= len(window.text) + 1:
            return BufferScanOutcome(last_result_line)
        collector = _LineMatchCollector(self, window, last_result_line, final)
        if self.params.literal:
            return self._search_literal(window, scan_start, scan_until, collector)
        if self.compiled_regex is None:
            return collector.outcome()
        return self._search_regex(window, scan_start, scan_until, collector)

    def _search_literal(self, window: TextWindow, scan_start: int, scan_until: int, collector: _LineMatchCollector) -> BufferScanOutcome:
        """Find literal starts, deferring incomplete previews and deduplicating lines.

        Args:
            window (TextWindow): Retained text and its absolute character/line coordinates.
            scan_start (int): First eligible match-start offset relative to the retained text window.
            scan_until (int): Exclusive match-start boundary relative to the retained window; final scans may use
                len(text) + 1.
            collector (_LineMatchCollector): Per-window line/deduplication state sharing this file's result sink.

        Returns:
            BufferScanOutcome: Last reported starting line and any deferred match requiring more preview text.
        """
        position = scan_start
        text = window.text
        while not self.page.full:
            match_start = text.find(self.params.query, position)
            if match_start < 0 or match_start >= scan_until:
                break

            # A short unfinished line needs another chunk for its complete preview.
            if needs_complete_line_preview(text, match_start, self.params.max_line_preview_chars, window.starts_mid_line, collector.final):
                return collector.outcome(window.start_offset + match_start)
            is_new_line = collector.add(match_start)
            if not is_new_line:
                next_line = text.find("\n", match_start)
                if next_line < 0:
                    break
                position = next_line + 1
            else:
                position = match_start + 1
        return collector.outcome()

    def _search_regex(self, window: TextWindow, scan_start: int, scan_until: int, collector: _LineMatchCollector) -> BufferScanOutcome:
        """Run timed matching without consuming starts beyond the committed boundary.

        Args:
            window (TextWindow): Retained text and its absolute character/line coordinates.
            scan_start (int): First eligible match-start offset relative to the retained text window.
            scan_until (int): Exclusive match-start boundary relative to the retained window; final scans may use
                len(text) + 1.
            collector (_LineMatchCollector): Per-window line/deduplication state sharing this file's result sink.

        Returns:
            BufferScanOutcome: Last reported line, deferred match and timeout outcome for this regex window.
        """
        assert self.compiled_regex is not None
        text = window.text
        try:
            matches = self.compiled_regex.finditer(text, pos=scan_start, timeout=self.params.regex_timeout_seconds)
            for match in matches:
                if match.start() >= scan_until or self.page.full:
                    break

                # Matches touching the current right edge can still change next read.
                if match.end() >= len(text) - 1 and not collector.final:
                    return collector.outcome(window.start_offset + match.start())
                preview_limit = min(self.params.max_line_preview_chars, self.params.max_context_chars)
                if needs_complete_line_preview(text, match.start(), preview_limit, window.starts_mid_line, collector.final):
                    return collector.outcome(window.start_offset + match.start())
                collector.add(match.start())
        except TimeoutError:
            logger.warning(
                "Regex search timed out for %s after %.3f seconds; remaining content in this file was skipped",
                self.file_path,
                self.params.regex_timeout_seconds,
            )
            return collector.outcome(regex_timed_out=True)
        return collector.outcome()
