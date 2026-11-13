"""General text primitives preserve detection and preview boundaries."""

import codecs

from pylizlib.core.data.text.encoding import EncodingDetector
from pylizlib.core.data.text.preview import line_preview, needs_complete_line_preview


def test_encoding_decisions_cover_bom_fallback_and_binary(tmp_path):
    """Detection retains UTF-32, Windows-1252 fallback and NUL rejection."""
    path = tmp_path / "content"
    detector = EncodingDetector()
    path.write_bytes(codecs.BOM_UTF32_LE + "needle".encode("utf-32-le"))
    decision = detector.detect(path, None)
    assert decision.encoding == "utf-32"
    assert not decision.binary
    path.write_bytes("caffè".encode("cp1252"))
    decision = detector.detect(path, None)
    assert decision.encoding == "cp1252"
    assert decision.used_fallback
    assert not decision.binary
    path.write_bytes(b"binary\x00content")
    assert detector.detect(path, None).binary
    assert not detector.detect(path, "utf-8").binary


def test_preview_defers_short_incomplete_lines_and_marks_truncation():
    """A streamed short line waits for completion; long previews expose ellipses."""
    assert needs_complete_line_preview("short", 0, 10, False, False)
    assert not needs_complete_line_preview("short\n", 0, 10, False, False)
    assert line_preview("  short  ", 2, 20, False, True) == "short"
    assert line_preview("abcdefghij", 5, 4, True, False) == "…efgh…"
