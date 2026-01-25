from typing import List, Optional

from rich.console import Console

from pylizlib.media.lizmedia import MediaListResult
from pylizlib.media.view.table import MediaListResultPrinter
from pylizlib.media.script.organizer.searcher_os import FileSystemSearcher
from pylizlib.media.script.organizer.searcher_eagle import EagleCatalogSearcher


class MediaSearcher:
    """
    Utility class to search for media files in a directory, optionally integrating with Eagle library
    or filtering by regex. Acts as a facade for specific search strategies.
    """

    def __init__(self, path: str):
        self.path = path
        self._result = MediaListResult()
        self._console = Console()

    def get_result(self) -> MediaListResult:
        return self._result

    def run_search_system(self, exclude: str = None, dry: bool = False):
        searcher = FileSystemSearcher(self.path)
        self._result = searcher.search(exclude, dry)

    def run_search_eagle(self, eagletag: Optional[List[str]] = None):
        searcher = EagleCatalogSearcher(self.path)
        searcher.search(eagletag)
        self._result = searcher.get_result()

    def printAcceptedAsTable(self, sort_index: int = 0):
        printer = MediaListResultPrinter(self._result)
        printer.print_accepted(sort_index)

    def printRejectedAsTable(self, sort_index: int = 0):
        printer = MediaListResultPrinter(self._result)
        printer.print_rejected(sort_index)

    def printErroredAsTable(self, sort_index: int = 0):
        printer = MediaListResultPrinter(self._result)
        printer.print_errored(sort_index)
