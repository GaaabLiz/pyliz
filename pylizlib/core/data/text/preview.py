"""Bounded line previews and deferral rules for streaming text matching."""


def needs_complete_line_preview(
    buffer: str,
    match_start: int,
    max_chars: int,
    buffer_starts_mid_line: bool,
    final: bool,
) -> bool:
    """Decide whether a short line needs another chunk before its preview is final.

    Args:
        buffer (str): Current decoded text window.
        match_start (int): Match start offset relative to buffer.
        max_chars (int): Positive maximum line-preview width, before ellipses.
        buffer_starts_mid_line (bool): Whether earlier characters of the first line were discarded, so waiting
            cannot reconstruct a complete line.
        final (bool): Whether the reader has reached EOF.

    Returns:
        bool: True only for an incomplete, untruncated short line without a newline.
    """
    if final or buffer_starts_mid_line or buffer.find("\n", match_start) >= 0:
        return False
    line_start = buffer.rfind("\n", 0, match_start) + 1
    return len(buffer) - line_start <= max_chars


def line_preview(
    buffer: str,
    match_start: int,
    max_chars: int,
    buffer_starts_mid_line: bool,
    final: bool,
) -> str:
    """Build a stripped line preview, adding ellipses for discarded characters.

    Args:
        buffer (str): Current decoded text window.
        match_start (int): Match start offset relative to buffer.
        max_chars (int): Positive character limit for the preview before ellipses.
        buffer_starts_mid_line (bool): Whether the beginning of the first line was removed from the rolling
            window.
        final (bool): Whether EOF makes the trailing line complete.

    Returns:
        str: Stripped preview around the match, up to max_chars plus ellipses; leading/trailing whitespace does
            not contribute to the final displayed text.
    """
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
