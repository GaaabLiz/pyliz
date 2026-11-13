"""Named window coordinates preserve the legacy trimming and deferral rules."""

from pathlib import Path

from pylizlib.core.data.text.matching import BufferMatcher
from pylizlib.core.data.text.models import TextSearchOptions
from pylizlib.core.data.text.results import ResultPage
from pylizlib.core.data.text.window import TextWindow


def test_tail_has_independent_coordinates_and_keeps_line_boundaries():
    """EOF trimming must not advance the main streaming window a second time."""
    window = TextWindow()
    window.append("one\nabc", 5)
    assert (window.text, window.start_offset, window.start_line, window.starts_mid_line) == ("e\nabc", 2, 1, True)
    tail = window.tail(3)
    assert (tail.text, tail.start_offset, tail.start_line, tail.starts_mid_line) == ("abc", 4, 2, False)
    assert (window.text, window.start_offset, window.start_line) == ("e\nabc", 2, 1)


def test_named_outcome_defers_incomplete_preview_until_eof():
    """A pending match retains an absolute offset instead of consuming the page."""
    page = ResultPage(0, 10)
    matcher = BufferMatcher(Path("file"), TextSearchOptions("needle"), None, page)
    window = TextWindow("needle", 100, 3)
    result = matcher.search(window, 0, 7, None, final=False)
    assert result.deferred_match == 100
    assert result.last_result_line is None
    assert not result.regex_timed_out
    assert page.results == []
    result = matcher.search(window, 0, 7, None, final=True)
    assert result.last_result_line == 3
    assert result.deferred_match is None
    assert [(match.line_number, match.line_content) for match in page.results] == [(3, "needle")]
