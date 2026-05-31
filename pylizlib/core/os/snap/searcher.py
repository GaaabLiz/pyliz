"""
Full-text and filename search across snapshot contents.

Responsibilities (Single Responsibility Principle):
    - Defining the search parameter model (query, type, target, extensions).
    - Searching the files inside one or more snapshots on the filesystem.
    - Returning structured results that describe where a match was found.

Classes:
    QueryType            – Enum: TEXT | REGEX.
    SearchTarget         – Enum: FILE_NAME | FILE_CONTENT.
    SnapshotSearchParams – Parameters for a search operation.
    SnapshotSearchResult – A single match found during a search.
    SnapshotSearcher     – Executes searches across snapshot directories.
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

from pylizlib.core.log.pylizLogger import logger
from pylizlib.core.os.snap.catalogue import SnapshotCatalogue
from pylizlib.core.os.snap.domain import Snapshot

# Type alias for a progress callback: (filename, total_files, processed_files) -> None
SnapshotProgressCallback = Callable[[str, int, int], None]


class QueryType(Enum):
    """Specifies whether a search query is plain text or a regular expression."""

    TEXT = "text"
    REGEX = "regex"


class SearchTarget(Enum):
    """Specifies whether to search for a file name or within file content."""

    FILE_NAME = "name"
    FILE_CONTENT = "content"


@dataclass
class SnapshotSearchResult:
    """
    Represents a single search result within a snapshot file.
    Can be a match in file content or a match of a file name.
    """

    file_path: Path
    searched_text: str
    snapshot_name: str
    line_number: Optional[int] = None
    line_content: Optional[str] = None


@dataclass
class SnapshotSearchParams:
    """
    Parameters for searching within a snapshot.
    """

    query: str
    search_target: SearchTarget = SearchTarget.FILE_CONTENT
    query_type: QueryType = QueryType.TEXT
    extensions: list[str] = field(default_factory=list)


class SnapshotSearcher:
    """
    Searches for textual content within the files of one or more snapshots.
    """

    def __init__(self, catalogue: SnapshotCatalogue):
        """
        Initializes the SnapshotSearcher.

        Args:
            catalogue: The SnapshotCatalogue to search in.
        """
        self.catalogue = catalogue

    def search(
        self,
        snapshot: Snapshot,
        params: SnapshotSearchParams,
        on_progress: Optional[SnapshotProgressCallback] = None,
    ) -> list[SnapshotSearchResult]:
        """
        Performs a search in a single snapshot based on the provided parameters.

        Args:
            snapshot: The `Snapshot` object to search within.
            params: An object containing the search query and options.
            on_progress: An optional callback function to report search progress,
                         receiving (filename, total_files, processed_files).

        Returns:
            A list of `SnapshotSearchResult` objects matching the query.
        """
        snapshot_path = self.catalogue.get_snap_directory_path(snapshot)

        compiled_regex = None
        if params.query_type == QueryType.REGEX:
            try:
                compiled_regex = re.compile(params.query)
            except re.error as e:
                logger.error(f"Invalid regex pattern provided: {e}")
                return []

        return self._search_in_snapshot_path(snapshot, snapshot_path, params, compiled_regex, on_progress)

    def search_list(
        self,
        snapshots: list[Snapshot],
        params: SnapshotSearchParams,
        on_progress: Optional[SnapshotProgressCallback] = None,
    ) -> list[SnapshotSearchResult]:
        """
        Performs a search across a list of snapshots based on the provided parameters.

        Args:
            snapshots: A list of Snapshot objects to search within.
            params: The search parameters (query, type, extensions).
            on_progress: An optional callback to report progress.

        Returns:
            A list of all search results found across all specified snapshots.
        """
        all_results: list[SnapshotSearchResult] = []
        for snapshot in snapshots:
            all_results.extend(self.search(snapshot, params, on_progress))
        return all_results

    def _search_in_snapshot_path(
        self,
        snapshot: Snapshot,
        snapshot_path: Path,
        params: SnapshotSearchParams,
        compiled_regex: Optional[re.Pattern],
        on_progress: Optional[SnapshotProgressCallback],
    ) -> list[SnapshotSearchResult]:
        """
        Private helper to perform a search within a specific snapshot's directory path.

        Args:
            snapshot: The snapshot being searched.
            snapshot_path: The filesystem path of the snapshot's contents.
            params: The search parameters.
            compiled_regex: A pre-compiled regex pattern, if applicable.
            on_progress: The progress callback function.

        Returns:
            A list of search results found in the snapshot.
        """
        results: list[SnapshotSearchResult] = []
        if not snapshot_path or not snapshot_path.is_dir():
            logger.warning(f"Snapshot path '{snapshot_path}' for snapshot id '{snapshot.id}' does not exist or is not a directory.")
            return results

        # 1. Collect all files to be searched
        files_to_search: list[Path] = []
        for dir_assoc in snapshot.directories:
            copied_dir_path = snapshot_path.joinpath(dir_assoc.directory_name)
            if not copied_dir_path.is_dir():
                continue
            for file_path in copied_dir_path.rglob("*"):
                if self._should_search_file(file_path, params.extensions):
                    files_to_search.append(file_path)

        # 2. Iterate and report progress
        total_files = len(files_to_search)
        for i, file_path in enumerate(files_to_search):
            if on_progress:
                on_progress(file_path.name, total_files, i + 1)

            if params.search_target == SearchTarget.FILE_NAME:
                found = False
                if params.query_type == QueryType.TEXT:
                    if params.query in file_path.name:
                        found = True
                elif compiled_regex and compiled_regex.search(file_path.name):
                    found = True

                if found:
                    results.append(
                        SnapshotSearchResult(
                            file_path=file_path,
                            searched_text=params.query,
                            snapshot_name=snapshot.name,
                        )
                    )

            elif params.search_target == SearchTarget.FILE_CONTENT:
                results.extend(self._search_in_file(file_path, params, compiled_regex, snapshot.name))

        return results

    def _should_search_file(self, file_path: Path, extensions: list[str]) -> bool:
        """
        Determines if a file should be included in the search.

        Args:
            file_path: The path to the file.
            extensions: A list of file extensions to include. If empty, all files are included.

        Returns:
            True if the file should be searched, False otherwise.
        """
        if not file_path.is_file():
            return False
        if not extensions:
            return True  # If no extensions are specified, search all files
        return file_path.suffix in extensions

    def _search_in_file(
        self,
        file_path: Path,
        params: SnapshotSearchParams,
        compiled_regex: Optional[re.Pattern],
        snapshot_name: str,
    ) -> list[SnapshotSearchResult]:
        """
        Performs the search within a single file.

        Args:
            file_path: The path of the file to search.
            params: The search parameters.
            compiled_regex: A pre-compiled regex pattern, if applicable.
            snapshot_name: The name of the snapshot for including in results.

        Returns:
            A list of search results found within the file.
        """
        results: list[SnapshotSearchResult] = []
        try:
            with file_path.open("r", encoding="utf-8") as f:
                for i, line in enumerate(f, 1):
                    found = False
                    if params.query_type == QueryType.TEXT:
                        if params.query in line:
                            found = True
                    elif compiled_regex and compiled_regex.search(line):
                        found = True

                    if found:
                        results.append(
                            SnapshotSearchResult(
                                file_path=file_path,
                                searched_text=params.query,
                                line_number=i,
                                line_content=line.strip(),
                                snapshot_name=snapshot_name,
                            )
                        )
        except UnicodeDecodeError:
            logger.debug(f"Skipping binary file during search: {file_path}")
        except Exception as e:
            logger.warning(f"Error reading file {file_path} during search: {e}")
        return results
