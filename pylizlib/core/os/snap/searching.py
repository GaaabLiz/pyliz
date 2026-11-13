"""Adapt live snapshot search settings and results to the general text engine."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pylizlib.core.data.text.results import ResultPage
from pylizlib.core.data.text.search import TextMatch

if TYPE_CHECKING:
    from pylizlib.core.os.snap.searcher import SnapshotSearchParams, SnapshotSearchResult


class SnapshotTextOptions:
    """Expose live parameters without copying mutable callback-visible settings.

    Attributes:
        params (SnapshotSearchParams): Query, encoding and resource limits; the search observes this live
            configuration.
    """

    def __init__(self, params: SnapshotSearchParams):
        """Retain the caller's search parameters by reference.

        Args:
            params (SnapshotSearchParams): Validated snapshot query and limits.

        Returns:
            None: Property reads continue to observe subsequent caller mutations.
        """
        self.params = params

    @property
    def query(self) -> str:
        """Return str: current query text or regular-expression source.

        Returns:
            str: Current query text or regular-expression source.
        """
        return self.params.query

    @property
    def literal(self) -> bool:
        """Return bool: whether the current query mode is literal text.

        Returns:
            bool: Whether the current query mode is literal text.
        """
        from pylizlib.core.os.snap.searcher import QueryType

        return self.params.query_type == QueryType.TEXT

    @property
    def encoding(self) -> str | None:
        """Return str | None: explicit codec or automatic-detection selection.

        Returns:
            str | None: Explicit codec or automatic-detection selection.
        """
        return self.params.encoding

    @property
    def chunk_size(self) -> int:
        """Return int: decoded characters requested from each stream read.

        Returns:
            int: Decoded characters requested from each stream read.
        """
        return self.params.chunk_size

    @property
    def max_context_chars(self) -> int:
        """Return int: current maximum regex context in decoded characters.

        Returns:
            int: Current maximum regex context in decoded characters.
        """
        return self.params.max_context_chars

    @property
    def max_line_preview_chars(self) -> int:
        """Return int: current preview width before any truncation ellipses.

        Returns:
            int: Current preview width before any truncation ellipses.
        """
        return self.params.max_line_preview_chars

    @property
    def regex_timeout_seconds(self) -> float:
        """Return float: timeout for each regex matching operation in seconds.

        Returns:
            float: Timeout for each regex matching operation in seconds.
        """
        return self.params.regex_timeout_seconds


class SnapshotMatchPage:
    """Convert generic text matches while preserving snapshot pagination state.

    Attributes:
        page (ResultPage[SnapshotSearchResult]): Bounded result sink retaining remaining offset, limit and
            successful matches.
        snapshot_name (str): Snapshot display label copied into each public search result.
    """

    def __init__(self, page: ResultPage[SnapshotSearchResult], snapshot_name: str):
        """Bind a caller-owned page and the snapshot label for this file.

        Args:
            page (ResultPage[SnapshotSearchResult]): Page mutated by accepted matches.
            snapshot_name (str): Snapshot label copied into each public result.

        Returns:
            None: No matches are added until add or commit is called.
        """
        self.page = page
        self.snapshot_name = snapshot_name

    @property
    def full(self) -> bool:
        """Return bool: whether the underlying page has reached its result limit.

        Returns:
            bool: Whether this bounded page has reached its configured result limit.
        """
        return self.page.full

    def add(self, result: TextMatch) -> None:
        """Convert a generic match and apply the existing offset/limit policy.

        Args:
            result (TextMatch): Matching file, query, starting line and preview.

        Returns:
            None: The underlying page consumes or retains the converted result.
        """
        from pylizlib.core.os.snap.searcher import SnapshotSearchResult

        self.page.add(SnapshotSearchResult(result.file_path, result.query, self.snapshot_name, result.line_number, result.line_content))

    def fork(self) -> SnapshotMatchPage:
        """Return SnapshotMatchPage: an isolated file attempt with remaining limits.

        Returns:
            SnapshotMatchPage: Independent attempt with the remaining offset and capacity; its results can be
                discarded without mutating the parent.
        """
        return SnapshotMatchPage(self.page.fork(), self.snapshot_name)

    def commit(self, child: SnapshotMatchPage) -> None:
        """Merge a completed attempt while retaining caller-owned page identity.

        Args:
            child (SnapshotMatchPage): Successful attempt forked from this page.

        Returns:
            None: Retained results and consumed offset are merged into the parent.
        """
        self.page.commit(child.page)
