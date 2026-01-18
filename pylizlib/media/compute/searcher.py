import os
import re
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
                        try:
                            liz_media = LizMedia(file_path)
                            result.rejected.append(LizMediaSearchResult(
                                status=MediaStatus.REJECTED,
                                media=liz_media,
                                reason="Rejected by regex pattern"
                            ))
                        except ValueError:
                             pass
                        pbar.update(1)
                        continue

                    try:
                        liz_media = LizMedia(file_path)
                        result.accepted.append(LizMediaSearchResult(
                            status=MediaStatus.ACCEPTED,
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
        reader = EagleCoolReader(Path(self.path), file_types=[FileType.IMAGE, FileType.VIDEO, FileType.AUDIO])
        
        # Run the reader to populate findings (blocking operation with its own progress bar)
        reader.run()
        
        # Process found media with progress bar
        with tqdm(reader.items, desc="Filtering Eagle Media", unit="items") as pbar:
            for eagle in pbar:
                # Update description to show current file
                pbar.set_description(f"Filtering {eagle.file_path.name}")
                
                try:
                    if self._filter_by_tag(eagle, eagletag):
                        lizmedia = LizMedia(eagle.file_path)
                        lizmedia.attach_eagle_metadata(eagle.metadata)
                        
                        self._result.accepted.append(LizMediaSearchResult(
                            status=MediaStatus.ACCEPTED,
                            media=lizmedia
                        ))
                except ValueError as e:
                    tqdm.write(f"[red]Error: {eagle.file_path}: {e}[/red]")
                    try:
                        self._result.rejected.append(LizMediaSearchResult(
                            status=MediaStatus.REJECTED,
                            media=LizMedia(eagle.file_path),
                            reason=f"Error loading media: {e}"
                        ))
                    except ValueError:
                        pass
                
                pbar.update(1)
            
            pbar.set_description("Scanning complete")

        # Handle errors found during reading
        print("\n")
        for error_path, reason in reader.error_paths:
            print(f"[red]SKIPPED Eagle Directory {error_path} because of error: {reason}[/red]")
        for skipped_path, reason in reader.skipped_path:
            print(f"[yellow]SKIPPED Eagle Directory {skipped_path} because: {reason}[/yellow]")

        print("\n[bold cyan]Eagle Search Summary:[/bold cyan]")
        print(f"  Scanned folders: {reader.scanned_folders_count}")
        print(f"  File types: {', '.join([ft.name for ft in reader.file_types])}")
        print(f"  Eagle Items created: {len(reader.items)}")
        print(f"  Accepted items: {len(self._result.accepted)}")
        print(f"  Rejected items: {len(self._result.rejected)}")
        print(f"  Skipped in reader: {len(reader.skipped_path)}")
        print(f"  Errors in reader: {len(reader.error_paths)}")

    def _filter_by_tag(self, eagle, eagletag: Optional[List[str]]) -> bool:
        """
        Checks if the eagle media matches the tag criteria.
        Returns True if accepted, False if rejected (and appends to self._result.rejected).
        """
        if not eagletag:
            return True

        if not eagle.metadata:
            try:
                self._result.rejected.append(LizMediaSearchResult(
                    status=MediaStatus.REJECTED,
                    media=LizMedia(eagle.file_path),
                    reason="Missing metadata for tag filtering"
                ))
            except ValueError:
                pass
            return False

        if not any(tag in eagle.metadata.tags for tag in eagletag):
            try:
                self._result.rejected.append(LizMediaSearchResult(
                    status=MediaStatus.REJECTED,
                    media=LizMedia(eagle.file_path),
                    reason="Tag mismatch"
                ))
            except ValueError:
                pass
            return False
            
        return True


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
        # We need to extract the LizMedia object for sorting
        sorted_results = self._sort_result_list(self._result.accepted, sort_index)

        table = Table(title=f"Accepted Media Files ({len(self._result.accepted)})")
        table.add_column("Filename", style="cyan", no_wrap=True)
        table.add_column("Creation Date", style="blue")
        table.add_column("Has EXIF", justify="center", style="magenta")
        table.add_column("Ext", justify="center", style="yellow")
        table.add_column("Size (MB)", justify="right", style="green")

        for item in sorted_results:
            media = item.media
            has_exif = "Yes" if media.has_exif_data else "No"
            creation_date = media.creation_date_from_exif_or_file.strftime("%Y-%m-%d %H:%M:%S")
            
            table.add_row(
                media.file_name,
                creation_date,
                has_exif,
                media.extension,
                f"{media.size_mb:.2f}"
            )

        self._console.print(table)

    def printRejectedAsTable(self, sort_index: int = 0):
        if not self._result.rejected:
            print("[green]No media files were rejected.[/green]")
            return
            
        # Sort rejected list based on index
        sorted_results = self._sort_result_list(self._result.rejected, sort_index)

        table = Table(title=f"Rejected Media Files ({len(self._result.rejected)})")
        table.add_column("Filename", style="red", no_wrap=True)
        table.add_column("Creation Date", style="blue")
        table.add_column("Has EXIF", justify="center", style="magenta")
        table.add_column("Size (MB)", justify="right", style="green")
        table.add_column("Reject reason", style="white")

        for item in sorted_results:
            media = item.media
            has_exif = "Yes" if media.has_exif_data else "No"
            creation_date = media.creation_date_from_exif_or_file.strftime("%Y-%m-%d %H:%M:%S")

            table.add_row(
                media.file_name,
                creation_date,
                has_exif,
                f"{media.size_mb:.2f}",
                item.reason
            )

        self._console.print(table)

    def _sort_result_list(self, results: List[LizMediaSearchResult], sort_index: int) -> List[LizMediaSearchResult]:
        if sort_index == 1:
            return sorted(results, key=lambda x: x.media.creation_date_from_exif_or_file)
        elif sort_index == 2:
            return sorted(results, key=lambda x: x.media.has_exif_data)
        elif sort_index == 3:
            return sorted(results, key=lambda x: x.media.extension)
        elif sort_index == 4:
            return sorted(results, key=lambda x: x.media.size_mb)
        else:
            # Default to filename (index 0 or invalid)
            return sorted(results, key=lambda x: x.media.file_name)
