"""Named text-window coordinates and matching outcomes for bounded streaming."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TextWindow:
    """Track retained text and its position in the decoded file.

    Attributes:
        text (str): Retained suffix of the decoded stream.
        start_offset (int): Zero-based absolute character offset of text[0].
        start_line (int): One-based line number containing text[0].
        starts_mid_line (bool): Whether discarded text ended before a newline.
    """

    text: str = ""
    start_offset: int = 0
    start_line: int = 1
    starts_mid_line: bool = False

    def append(self, chunk: str, limit: int) -> None:
        """Append decoded text and retain the last limit characters.

        Args:
            chunk (str): Next decoded chunk, after universal-newline conversion.
            limit (int): Maximum retained character count for this scan.

        Returns:
            None: Text and coordinates are updated in place using the existing rule for whether the retained first
                line is incomplete.
        """
        self.text += chunk
        self._trim(limit)

    def tail(self, limit: int) -> TextWindow:
        """Copy this window and trim only the copy for the final EOF scan.

        Args:
            limit (int): Final maximum retained characters.

        Returns:
            TextWindow: Independent coordinates and suffix; this window is unchanged.
        """
        result = TextWindow(self.text, self.start_offset, self.start_line, self.starts_mid_line)
        result._trim(limit)
        return result

    def _trim(self, limit: int) -> None:
        """Drop a prefix while advancing absolute character and line coordinates.

        Args:
            limit (int): Maximum character count to retain.

        Returns:
            None: Unchanged when text already fits; otherwise records the dropped suffix boundary exactly as the
                previous streaming implementation did.
        """
        dropped_count = max(0, len(self.text) - limit)
        if dropped_count:
            dropped = self.text[:dropped_count]
            self.text = self.text[dropped_count:]
            self.start_offset += dropped_count
            self.start_line += dropped.count("\n")
            self.starts_mid_line = not dropped.endswith("\n")


@dataclass(frozen=True)
class BufferScanOutcome:
    """Name the independent results of matching one retained window.

    Attributes:
        last_result_line (int | None): Last reported starting line for deduplication.
        deferred_match (int | None): Absolute start to retry after another chunk.
        regex_timed_out (bool): Whether the current file's remaining scan must stop.
    """

    last_result_line: int | None
    deferred_match: int | None = None
    regex_timed_out: bool = False
