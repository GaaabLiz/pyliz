from datetime import datetime
from typing import List, Any, Callable

from rich.console import Console
from rich.table import Table

from pylizlib.media.lizmedia2 import LizMediaSearchResult, MediaListResult


class OrganizerTablePrinter:
    def __init__(self, result: MediaListResult):
        self._result = result
        self._console = Console()

    def print_accepted(self, sort_index: int = 0):
        if not self._result.accepted:
            print("[yellow]No accepted media files found.[/yellow]")
            return

        self._print_generic_table(
            title=f"Accepted Media Files ({len(self._result.accepted)})",
            items=self._result.accepted,
            sort_index=sort_index,
            columns=[
                ("Index", "dim", "right"),
                ("Filename", "cyan", None),
                ("Creation Date", "blue", None),
                ("Has EXIF", "magenta", "center"),
                ("Ext", "yellow", "center"),
                ("Size (MB)", "green", "right"),
                ("Sidecars", "white", None)
            ],
            row_extractor=self._extract_accepted_row,
            table_type="accepted"
        )

    def print_rejected(self, sort_index: int = 0):
        if not self._result.rejected:
            print("[green]No media files were rejected.[/green]")
            return

        self._print_generic_table(
            title=f"Rejected Media Files ({len(self._result.rejected)})",
            items=self._result.rejected,
            sort_index=sort_index,
            columns=[
                ("Index", "dim", "right"),
                ("Filename", "red", None),
                ("Creation Date", "blue", None),
                ("Has EXIF", "magenta", "center"),
                ("Size (MB)", "green", "right"),
                ("Reject reason", "white", None)
            ],
            row_extractor=self._extract_rejected_row,
            table_type="rejected"
        )

    def print_errored(self, sort_index: int = 0):
        if not self._result.errored:
            print("[green]No media files were errored.[/green]")
            return

        self._print_generic_table(
            title=f"Errored Media Files ({len(self._result.errored)})",
            items=self._result.errored,
            sort_index=sort_index,
            columns=[
                ("Index", "dim", "right"),
                ("Filename", "red", None),
                ("Path", "magenta", None),
                ("Error reason", "white", None)
            ],
            row_extractor=self._extract_errored_row,
            table_type="errored"
        )

    def _print_generic_table(
            self, 
            title: str, 
            items: List[LizMediaSearchResult], 
            sort_index: int, 
            columns: List[tuple], 
            row_extractor: Callable[[LizMediaSearchResult], List[str]],
            table_type: str = "accepted"
    ):
        # Sort items
        sorted_items = self._sort_result_list(items, sort_index, table_type)

        table = Table(title=title)
        
        # Add columns with sorting indicator
        for idx, (name, style, justify) in enumerate(columns):
            header = f"{name}{' *' if sort_index == idx else ''}"
            kwargs = {}
            if style: kwargs["style"] = style
            if justify: kwargs["justify"] = justify
            if name == "Filename": kwargs["no_wrap"] = True
            
            table.add_column(header, **kwargs)

        # Add rows
        for item in sorted_items:
            table.add_row(*row_extractor(item))

        self._console.print(table)

    def _sort_result_list(self, results: List[LizMediaSearchResult], sort_index: int, table_type: str = "accepted") -> List[LizMediaSearchResult]:
        if sort_index == 0:
            return sorted(results, key=lambda x: x.index)
        elif sort_index == 1:
            return sorted(results, key=lambda x: x.media.file_name if x.media else x.path.name)
        elif sort_index == 2:
            return sorted(results, key=lambda x: x.media.creation_date_from_exif_or_file if x.media else datetime.min)
        elif sort_index == 3:
            return sorted(results, key=lambda x: x.media.has_exif_data if x.media else False)
        
        if table_type == "rejected":
            if sort_index == 4: # Size
                return sorted(results, key=lambda x: x.media.size_mb if x.media else 0)
            elif sort_index == 5: # Reason
                return sorted(results, key=lambda x: x.reason)
        else: # accepted / default / errored
            if sort_index == 4: # Extension
                return sorted(results, key=lambda x: x.media.extension if x.media else x.path.suffix.lower())
            elif sort_index == 5: # Size
                return sorted(results, key=lambda x: x.media.size_mb if x.media else 0)
        
        return results

    def _extract_accepted_row(self, item: LizMediaSearchResult) -> List[str]:
        media = item.media
        has_exif = "Yes" if media.has_exif_data else "No"
        creation_date = media.creation_date_from_exif_or_file.strftime("%Y-%m-%d %H:%M:%S")
        sidecars_str = ", ".join([s.name for s in item.sidecar_files]) if item.sidecar_files else ""
        
        return [
            str(item.index),
            media.file_name,
            creation_date,
            has_exif,
            media.extension,
            f"{media.size_mb:.2f}",
            sidecars_str
        ]

    def _extract_rejected_row(self, item: LizMediaSearchResult) -> List[str]:
        media = item.media
        if media:
            filename = media.file_name
            has_exif = "Yes" if media.has_exif_data else "No"
            creation_date = media.creation_date_from_exif_or_file.strftime("%Y-%m-%d %H:%M:%S")
            size_mb = f"{media.size_mb:.2f}"
        else:
            filename = item.path.name
            has_exif = "N/A"
            creation_date = "N/A"
            size_mb = "N/A"

        return [
            str(item.index),
            filename,
            creation_date,
            has_exif,
            size_mb,
            item.reason
        ]

    def _extract_errored_row(self, item: LizMediaSearchResult) -> List[str]:
        return [
            str(item.index),
            item.path.name,
            str(item.path),
            item.reason
        ]
