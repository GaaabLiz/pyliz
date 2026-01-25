from datetime import datetime
from typing import List, Any, Callable, Optional

from rich.console import Console
from rich.table import Table

from pylizlib.media.lizmedia import LizMediaSearchResult, MediaListResult


class MediaListResultPrinter:
    def __init__(self, result: MediaListResult):
        self._result = result
        self._console = Console()

    def print_accepted(self, sort_index: int = 0):
        if not self._result.accepted:
            self._console.print("[yellow]No accepted media files found.[/yellow]")
            return

        self._print_generic_table(
            title=f"Accepted Media Files ({len(self._result.accepted)})",
            items=self._result.accepted,
            sort_index=sort_index,
            extra_columns=[("Sidecars", "white", None)],
            table_type="accepted"
        )

    def print_rejected(self, sort_index: int = 0):
        if not self._result.rejected:
            self._console.print("[green]No media files were rejected.[/green]")
            return

        self._print_generic_table(
            title=f"Rejected Media Files ({len(self._result.rejected)})",
            items=self._result.rejected,
            sort_index=sort_index,
            extra_columns=[("Reason", "white", None)],
            table_type="rejected"
        )

    def print_errored(self, sort_index: int = 0):
        if not self._result.errored:
            self._console.print("[green]No media files were errored.[/green]")
            return

        self._print_generic_table(
            title=f"Errored Media Files ({len(self._result.errored)})",
            items=self._result.errored,
            sort_index=sort_index,
            extra_columns=[("Reason", "white", None)],
            table_type="errored"
        )

    def _print_generic_table(
            self, 
            title: str, 
            items: List[LizMediaSearchResult], 
            sort_index: int, 
            extra_columns: List[tuple], 
            table_type: str = "accepted"
    ):
        # Base columns for all tables
        base_columns = [
            ("Index", "dim", "right"),
            ("Filename", "cyan", None),
            ("Creation Date", "blue", None),
            ("Exif", "magenta", "center"),
            ("Ext", "yellow", "center"),
            ("Size (MB)", "green", "right"),
        ]
        
        all_columns = base_columns + extra_columns
        
        # Sort items using the shared logic
        sorted_items = self._sort_result_list(items, sort_index)

        table = Table(title=title)
        
        # Add columns with sorting indicator
        for idx, (name, style, justify) in enumerate(all_columns):
            header = f"{name}{' *' if sort_index == idx else ''}"
            kwargs = {}
            if style: kwargs["style"] = style
            if justify: kwargs["justify"] = justify
            if name == "Filename" or name == "Path": kwargs["no_wrap"] = True
            
            table.add_column(header, **kwargs)

        # Add rows
        for item in sorted_items:
            row = self._extract_common_row_data(item)
            
            # Append extra data based on table type
            if table_type == "accepted":
                sidecars_str = ", ".join([s.name for s in item.sidecar_files]) if item.sidecar_files else ""
                row.append(sidecars_str)
            else: # rejected or errored
                row.append(item.reason)
                
            table.add_row(*row)

        self._console.print(table)

    def _extract_common_row_data(self, item: LizMediaSearchResult) -> List[str]:
        """Extracts the 6 base columns shared by all tables."""
        media = item.media
        if media:
            filename = media.file_name
            creation_date = media.creation_date_from_exif_or_file.strftime("%Y-%m-%d %H:%M:%S")
            has_exif = "Yes" if media.has_exif_data else "No"
            ext = media.extension
            size_mb = f"{media.size_mb:.2f}"
        else:
            filename = item.path.name
            creation_date = "N/A"
            has_exif = "N/A"
            ext = item.path.suffix.lower()
            size_mb = "N/A"
            
        return [
            str(item.index),
            filename,
            creation_date,
            has_exif,
            ext,
            size_mb
        ]

    def _sort_result_list(self, results: List[LizMediaSearchResult], sort_index: int) -> List[LizMediaSearchResult]:
        """
        Unified sorting logic based on the 6 shared columns + 1 extra.
        Indices: 0=Index, 1=Filename, 2=Date, 3=Exif, 4=Ext, 5=Size, 6=Extra (Sidecars/Reason)
        """
        if sort_index == 0: # Index
            return sorted(results, key=lambda x: x.index)
        elif sort_index == 1: # Filename
            return sorted(results, key=lambda x: x.media.file_name if x.media else x.path.name)
        elif sort_index == 2: # Date
            return sorted(results, key=lambda x: x.media.creation_date_from_exif_or_file if x.media else datetime.min)
        elif sort_index == 3: # Exif
            return sorted(results, key=lambda x: x.media.has_exif_data if x.media else False)
        elif sort_index == 4: # Ext
            return sorted(results, key=lambda x: x.media.extension if x.media else x.path.suffix.lower())
        elif sort_index == 5: # Size
            return sorted(results, key=lambda x: x.media.size_mb if x.media else 0)
        elif sort_index == 6: # Extra (Sidecars or Reason)
            # For Reason, we use x.reason. For Sidecars, maybe sort by number of sidecars?
            # Let's default to sorting by the reason string if it's not accepted
            return sorted(results, key=lambda x: (", ".join([s.name for s in x.sidecar_files]) if x.sidecar_files else "") if not x.reason else x.reason)
        
        return results