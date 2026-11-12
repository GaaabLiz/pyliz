"""Bounded generic result pages supporting isolated attempts and offset rollback."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, TypeVar

ResultT = TypeVar("ResultT")


@dataclass
class ResultPage(Generic[ResultT]):
    """Collect one bounded result page while counting skipped matches."""

    offset_remaining: int
    limit: int
    results: list[ResultT] = field(default_factory=list)

    @property
    def full(self) -> bool:
        """Return whether this page has reached its configured result limit."""
        return len(self.results) >= self.limit

    def add(self, result: ResultT) -> None:
        """Skip earlier matches and retain only results that fit this page."""
        if self.offset_remaining:
            self.offset_remaining -= 1
        elif not self.full:
            self.results.append(result)

    def fork(self) -> ResultPage:
        """Create a file-local page that can be discarded after a decode retry."""
        return ResultPage(self.offset_remaining, self.limit - len(self.results))

    def commit(self, child: ResultPage) -> None:
        """Add a completed file's page and skipped-match count to this page."""
        self.offset_remaining = child.offset_remaining
        self.results.extend(child.results)
