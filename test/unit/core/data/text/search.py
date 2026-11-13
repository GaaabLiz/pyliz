"""Test streaming file search without constructing a snapshot or catalogue."""

import subprocess
import sys

import pytest
import regex

from pylizlib.core.data.text.results import ResultPage
from pylizlib.core.data.text.search import TextFileSearcher, TextSearchOptions


@pytest.mark.parametrize("chunk_size", [1, 3, 8, 64])
def test_chunk_boundaries_do_not_change_literal_matches(tmp_path, chunk_size):
    """Repeated occurrences retain one result per starting line across all chunks."""
    path = tmp_path / "text"
    path.write_text("first needle needle\nsecond\nlast needle\n", encoding="utf-8")
    params = TextSearchOptions("needle", chunk_size=chunk_size, max_context_chars=100, max_line_preview_chars=30)
    page = ResultPage(0, 10)
    assert TextFileSearcher().search_file(path, params, None, page, None) is False
    assert [(match.line_number, match.line_content) for match in page.results] == [(1, "first needle needle"), (3, "last needle")]


def test_rolling_window_retains_legacy_preview_truncation(tmp_path):
    """Preserve the characterized preview when a small rolling window advances."""
    path = tmp_path / "text"
    path.write_text("first needle needle\nsecond\nlast needle\n", encoding="utf-8")
    params = TextSearchOptions("needle", chunk_size=1, max_context_chars=20, max_line_preview_chars=30)
    page = ResultPage(0, 10)
    TextFileSearcher().search_file(path, params, None, page, None)
    assert [(match.line_number, match.line_content) for match in page.results] == [(1, "first needle needle"), (3, "last needle…")]


def test_regex_multiline_and_callback_error_remain_distinct(tmp_path):
    """Matching can span lines, while observer errors propagate unchanged."""
    path = tmp_path / "text"
    path.write_text("first needle\nsecond\n", encoding="utf-8")
    params = TextSearchOptions("needle\\nsecond", literal=False, chunk_size=3, max_context_chars=100)
    page = ResultPage(0, 10)
    assert not TextFileSearcher().search_file(path, params, regex.compile(params.query), page, None)
    assert [match.line_number for match in page.results] == [1]
    original = RuntimeError("observer failed")

    def fail_observer():
        """Fail with a caller-owned exception instance."""
        raise original

    with pytest.raises(RuntimeError) as error:
        TextFileSearcher().search_file(path, params, regex.compile(params.query), ResultPage(0, 10), fail_observer)
    assert error.value is original


def test_timed_pattern_is_a_structural_capability(tmp_path):
    """A wrapper can supply matching and timeout support without C-type inheritance."""
    calls = []

    class RecordingPattern:
        """Delegate matching while recording the engine's requested timeout."""

        def finditer(self, text, *, pos, timeout):
            """Return real matches and retain the search bounds for assertions."""
            calls.append((pos, timeout))
            return regex.finditer("needle", text, pos=pos, timeout=timeout)

        def search(self, text, *, timeout):
            """Supply the filename-search part of the same capability."""
            return regex.search("needle", text, timeout=timeout)

    path = tmp_path / "text"
    path.write_text("first needle\nsecond needle\n", encoding="utf-8")
    params = TextSearchOptions("needle", literal=False, chunk_size=4, max_context_chars=100, regex_timeout_seconds=0.25)
    page = ResultPage(0, 10)
    assert TextFileSearcher().search_file(path, params, RecordingPattern(), page, None) is False
    assert [match.line_number for match in page.results] == [1, 2]
    assert calls and all(timeout == 0.25 for _, timeout in calls)


def test_text_engine_import_does_not_load_snapshots():
    """Reusable text search must remain independent from snapshot API imports."""
    code = "import sys; import pylizlib.core.data.text.search; assert not any(name.startswith('pylizlib.core.os.snap') for name in sys.modules)"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(("tail", "expected_count"), [("", 0), ("tail" * 10, 1)])
def test_regex_context_budget_is_not_a_hard_match_length_limit(tmp_path, tail, expected_count):
    """Preserve the legacy long-span behavior at chunk/EOF boundaries."""
    path = tmp_path / "text"
    path.write_text("a" + "x" * 50 + "b\n" + tail, encoding="utf-8")
    params = TextSearchOptions("a.*b", literal=False, chunk_size=200, max_context_chars=10, max_line_preview_chars=20)
    page = ResultPage(0, 10)
    TextFileSearcher().search_file(path, params, regex.compile(params.query), page, None)
    assert len(page.results) == expected_count
