import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import typer
from rich import print
from rich.console import Console
from rich.table import Table
from tqdm import tqdm

from pylizlib.core.domain.os import FileType
from pylizlib.eaglecool.reader import EagleCoolReader
from pylizlib.media.lizmedia2 import LizMedia, MediaListResult, LizMediaSearchResult, MediaStatus


class FileSystemSearcher:
    """
    Strategy class to search for media files in the file system.
    """
    def __init__(self, path: str):
        self.path = path

    def search(self, exclude: str = None, dry: bool = False) -> MediaListResult:
        result = MediaListResult()
        exclude_regex = None

        if exclude:
            try:
                exclude_regex = re.compile(exclude)
            except re.error as e:
                print(f"Error compiling regex '{exclude}': {e}")
                raise typer.Exit(code=1)

        # Use a single tqdm bar for the entire scanning process
        with tqdm(desc="Initializing scan...", unit="files") as pbar:
            for root, _, files in os.walk(self.path):
                for file in files:
                    file_path = Path(root) / file
                    pbar.set_description(f"Scanning {file}")
                    
                    # Check exclude pattern
                    if exclude_regex and exclude_regex.search(file):
                        if dry:
                            tqdm.write(f"  Skipping (regex match): {file}")
                        result.rejected.append(LizMediaSearchResult(
                            status=MediaStatus.REJECTED,
                            path=file_path,
                            media=None,
                            reason="Rejected by regex pattern"
                        ))
                        pbar.update(1)
                        continue

                    try:
                        liz_media = LizMedia(file_path)
                        result.accepted.append(LizMediaSearchResult(
                            status=MediaStatus.ACCEPTED,
                            path=file_path,
                            media=liz_media
                        ))
                    except ValueError:
                        # Not a media file, skip silently
                        pass
                    
                    pbar.update(1)
            
            pbar.set_description("Scanning complete")
        
        return result


class EagleCatalogSearcher:
    """
    Strategy class to search for media files using the Eagle library.
    """
    def __init__(self, path: str):
        self.path = path
        self._result = MediaListResult()

    def get_result(self) -> MediaListResult:
        return self._result

    def search(self, eagletag: Optional[List[str]] = None):
        self._result = MediaListResult() # Reset result on new search
        reader = EagleCoolReader(
            Path(self.path), 
            file_types=[FileType.IMAGE, FileType.VIDEO, FileType.AUDIO],
            filter_tags=eagletag
        )
        
        # Run the reader to populate findings (blocking operation with its own progress bar)
        reader.run()
        
        # Process found media with progress bar
        with tqdm(reader.items, desc="Processing Eagle Media", unit="items") as pbar:
            for eagle in pbar:
                # Update description to show current file
                pbar.set_description(f"Processing {eagle.file_path.name}")
                
                lizmedia = LizMedia(eagle.file_path)
                lizmedia.attach_eagle_metadata(eagle.metadata)
                
                self._result.accepted.append(LizMediaSearchResult(
                    status=MediaStatus.ACCEPTED,
                    path=eagle.file_path,
                    media=lizmedia
                ))
                
                pbar.update(1)
            
            pbar.set_description("Scanning complete")

        # Add reader skipped items to rejected
        for eagle_item, reason in tqdm(reader.items_skipped, desc="Processing Skipped Items", unit="items"):
            time.sleep(0.0005) # Simulate delay
            media_obj = None
            try:
                media_obj = LizMedia(eagle_item.file_path)
            except ValueError:
                pass

            self._result.rejected.append(LizMediaSearchResult(
                status=MediaStatus.REJECTED,
                path=eagle_item.file_path,
                media=media_obj,
                reason=reason
            ))

        # Add reader errors to errored
        for error_path, reason in tqdm(reader.error_paths, desc="Processing Reader Errors", unit="errors"):
            time.sleep(0.0005)
            self._result.errored.append(LizMediaSearchResult(
                status=MediaStatus.REJECTED,
                path=error_path,
                media=None,
                reason=reason
            ))

        # Post-process rejected items to link sidecars to accepted media
        sidecar_extensions = {'.xmp', '.aae'}
        accepted_map_by_stem = {item.path.stem: item for item in self._result.accepted}
        accepted_map_by_name = {item.path.name: item for item in self._result.accepted}
        rejected_to_keep = []

        for rejected_item in self._result.rejected:
            if rejected_item.path.suffix.lower() in sidecar_extensions:
                stem = rejected_item.path.stem
                
                # Check match by name (e.g. image.png.xmp -> matches image.png)
                if stem in accepted_map_by_name:
                    accepted_map_by_name[stem].sidecar_files.append(rejected_item.path)
                    continue
                
                # Check match by stem (e.g. image.xmp -> matches image.png)
                if stem in accepted_map_by_stem:
                    accepted_map_by_stem[stem].sidecar_files.append(rejected_item.path)
                    continue # Successfully linked, remove from rejected
            
            rejected_to_keep.append(rejected_item)
        
        self._result.rejected = rejected_to_keep

        print("\n[bold cyan]Eagle Search Summary:[/bold cyan]")
        print(f"  Scanned folders: {reader.scanned_folders_count}")
        print(f"  File types: {', '.join([ft.name for ft in reader.file_types])}")
        print(f"  Eagle Items created: {len(reader.items) + len(reader.items_skipped)}")
        print(f"  Accepted items: {len(self._result.accepted)}")
        print(f"  Rejected items: {len(self._result.rejected)}")
        print(f"  Errored items: {len(self._result.errored)}")
        
        total_sidecars = sum(len(item.sidecar_files) for item in self._result.accepted)
        print(f"  Sidecar files linked: {total_sidecars}")


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
        if not self._result.accepted:
            print("[yellow]No accepted media files found.[/yellow]")
            return
        
        # Sort media list based on index
        sorted_results = self._sort_result_list(self._result.accepted, sort_index)

        table = Table(title=f"Accepted Media Files ({len(self._result.accepted)})")
        table.add_column(f"Index{' *' if sort_index == 0 else ''}", style="dim", justify="right")
        table.add_column(f"Filename{' *' if sort_index == 1 else ''}", style="cyan", no_wrap=True)
        table.add_column(f"Creation Date{' *' if sort_index == 2 else ''}", style="blue")
        table.add_column(f"Has EXIF{' *' if sort_index == 3 else ''}", justify="center", style="magenta")
        table.add_column(f"Ext{' *' if sort_index == 4 else ''}", justify="center", style="yellow")
        table.add_column(f"Size (MB){' *' if sort_index == 5 else ''}", justify="right", style="green")
        table.add_column("Sidecars", style="white")

        for item in sorted_results:
            media = item.media
            has_exif = "Yes" if media.has_exif_data else "No"
            creation_date = media.creation_date_from_exif_or_file.strftime("%Y-%m-%d %H:%M:%S")
            
            sidecars_str = ", ".join([s.name for s in item.sidecar_files]) if item.sidecar_files else ""

            table.add_row(
                str(item.index),
                media.file_name,
                creation_date,
                has_exif,
                media.extension,
                f"{media.size_mb:.2f}",
                sidecars_str
            )

        self._console.print(table)

    def printRejectedAsTable(self, sort_index: int = 0):
        if not self._result.rejected:
            print("[green]No media files were rejected.[/green]")
            return
            
        # Sort rejected list based on index
        sorted_results = self._sort_result_list(self._result.rejected, sort_index)

        table = Table(title=f"Rejected Media Files ({len(self._result.rejected)})")
        table.add_column(f"Index{' *' if sort_index == 0 else ''}", style="dim", justify="right")
        table.add_column(f"Filename{' *' if sort_index == 1 else ''}", style="red", no_wrap=True)
        table.add_column(f"Creation Date{' *' if sort_index == 2 else ''}", style="blue")
        table.add_column(f"Has EXIF{' *' if sort_index == 3 else ''}", justify="center", style="magenta")
        table.add_column(f"Size (MB){' *' if sort_index == 5 else ''}", justify="right", style="green")
        table.add_column("Reject reason", style="white")

        for item in sorted_results:
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

            table.add_row(
                str(item.index),
                filename,
                creation_date,
                has_exif,
                size_mb,
                item.reason
            )

        self._console.print(table)

    def printErroredAsTable(self, sort_index: int = 0):
        if not self._result.errored:
            print("[green]No media files were errored.[/green]")
            return
            
        # Sort errored list based on index
        sorted_results = self._sort_result_list(self._result.errored, sort_index)

        table = Table(title=f"Errored Media Files ({len(self._result.errored)})")
        table.add_column(f"Index{' *' if sort_index == 0 else ''}", style="dim", justify="right")
        table.add_column(f"Filename{' *' if sort_index == 1 else ''}", style="red", no_wrap=True)
        table.add_column("Path", style="magenta")
        table.add_column("Error reason", style="white")

        for item in sorted_results:
            filename = item.path.name
            path_str = str(item.path)
            
            table.add_row(
                str(item.index),
                filename,
                path_str,
                item.reason
            )

        self._console.print(table)

    def _sort_result_list(self, results: List[LizMediaSearchResult], sort_index: int) -> List[LizMediaSearchResult]:
        if sort_index == 0:
            return sorted(results, key=lambda x: x.index)
        elif sort_index == 2:
            return sorted(results, key=lambda x: x.media.creation_date_from_exif_or_file if x.media else datetime.min)
        elif sort_index == 3:
            return sorted(results, key=lambda x: x.media.has_exif_data if x.media else False)
        elif sort_index == 4:
            return sorted(results, key=lambda x: x.media.extension if x.media else x.path.suffix.lower())
        elif sort_index == 5:
            return sorted(results, key=lambda x: x.media.size_mb if x.media else 0)
        else:
            # Default to filename (index 1 or invalid)
            return sorted(results, key=lambda x: x.media.file_name if x.media else x.path.name)
