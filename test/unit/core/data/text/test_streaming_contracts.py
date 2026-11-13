"""Preserve observed streaming semantics while replacing implicit scan state."""

import json
from pathlib import Path

import pytest
import regex

from pylizlib.core.data.text.results import ResultPage
from pylizlib.core.data.text.search import TextFileSearcher, TextSearchOptions

CASES = json.loads((Path(__file__).parent / "fixtures" / "streaming_contracts.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_characterized_streaming_results(tmp_path, case):
    """Window changes retain exact lines, previews, Unicode and retry behavior."""
    path = tmp_path / "content"
    path.write_bytes(case["content"].encode(case["codec"]))
    options = TextSearchOptions(**case["options"])
    compiled = regex.compile(options.query) if not options.literal else None
    page = ResultPage(0, 10)

    cancelled = TextFileSearcher().search_file(path, options, compiled, page, None)

    assert cancelled == case["cancelled"]
    assert [{"query": item.query, "line_number": item.line_number, "line_content": item.line_content} for item in page.results] == case["matches"]
