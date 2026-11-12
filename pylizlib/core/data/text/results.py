"""Bounded generic result pages supporting isolated attempts and offset rollback."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, TypeVar

ResultT = TypeVar("ResultT")


@dataclass
class ResultPage(Generic[ResultT]):
    """Collect one bounded result page while counting skipped matches.

    Attributes:
        offset_remaining (int): Number of eligible matches still to skip before retaining page results.
        limit (int): Maximum retained result count; full becomes True when len(results) reaches it.
        results (list[ResultT]): Retained results in traversal order; only a successful child attempt is merged.

    Notes:
        Callers supply non-negative offset and limit values; this low-level page
        does not introduce validation beyond the calling search configuration.
    """

    offset_remaining: int
    limit: int
    results: list[ResultT] = field(default_factory=list)

    @property
    def full(self) -> bool:
        """Return whether this page has reached its configured result limit.

        Returns:
            bool: Whether this bounded page has reached its configured result limit.
        """
        return len(self.results) >= self.limit

    def add(self, result: ResultT) -> None:
        """Skip earlier matches and retain only results that fit this page.

        Args:
            result (ResultT): Match or value to consume according to this bounded page's offset/limit.

        Returns:
            None: No return value.
        """
        if self.offset_remaining:
            self.offset_remaining -= 1
        elif not self.full:
            self.results.append(result)

    def fork(self) -> ResultPage:
        """Create a file-local page that can be discarded after a decode retry.

        Returns:
            ResultPage: Independent attempt with the remaining offset and capacity; its results can be discarded
                without mutating the parent.
        """
        return ResultPage(self.offset_remaining, self.limit - len(self.results))

    def commit(self, child: ResultPage) -> None:
        """Add a completed file's page and skipped-match count to this page.

        Args:
            child (ResultPage): Successful isolated result-page attempt whose matches and consumed offset are
                committed.

        Returns:
            None: No return value.
        """
        self.offset_remaining = child.offset_remaining
        self.results.extend(child.results)
