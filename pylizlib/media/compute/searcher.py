import os
import re
from pathlib import Path
from typing import List, Optional

import typer
from rich import print
from rich.console import Console
from rich.table import Table

from pylizlib.eaglecool.reader import EagleMediaReader
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

        print(f"Scanning directory: {self.path} ...")
        for root, _, files in os.walk(self.path):
            for file in files:
                file_path = Path(root) / file
                
                # Check exclude pattern
                if exclude_regex and exclude_regex.search(file):
                    if dry:
                        print(f"  Skipping (regex match): {file}")
                    try:
                        liz_media = LizMedia(file_path)
                        result.skipped.append(LizMediaSearchResult(
                            status=MediaStatus.SKIPPED,
                            media=liz_media,
                            reason="Excluded by regex pattern"
                        ))
                    except ValueError:
                         # Not a media file, so we ignore it even for skipped list usually? 
                         # Or we can track it as skipped non-media. 
                         # But LizMedia constructor raises ValueError if not media.
                         pass
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
        return result


class EagleCatalogSearcher:
    """
    Strategy class to search for media files using the Eagle library.
    """
    def __init__(self, path: str):
        self.path = path

    def search(self, eagletag: Optional[List[str]] = None) -> MediaListResult:
        result = MediaListResult()
        reader = EagleMediaReader(Path(self.path))
        eagles = reader.run()

        for eagle in eagles:
            try:
                if eagletag:
                    if not eagle.metadata:
                        print("[yellow]Warning: Eagle media without metadata, skipping tag filter.[/yellow]")
                        try:
                            result.skipped.append(LizMediaSearchResult(
                                status=MediaStatus.SKIPPED,
                                media=LizMedia(eagle.media_path),
                                reason="Missing metadata for tag filtering"
                            ))
                        except ValueError:
                            pass
                        continue
                    if not any(tag in eagle.metadata.tags for tag in eagletag):
                        print(f"[cyan]Eagle media {eagle.metadata.name} does not match specified tags, skipping.[/cyan]")
                        try:
                            result.skipped.append(LizMediaSearchResult(
                                status=MediaStatus.SKIPPED,
                                media=LizMedia(eagle.media_path),
                                reason="Tag mismatch"
                            ))
                        except ValueError:
                            pass
                        continue

                lizmedia = LizMedia(eagle.media_path)
                lizmedia.attach_eagle_metadata(eagle.metadata)
                
                result.accepted.append(LizMediaSearchResult(
                    status=MediaStatus.ACCEPTED,
                    media=lizmedia
                ))
                print(f"[green]Added Eagle media: {eagle.media_path}[/green]")
            except ValueError as e:
                print(f"[red]Error: {eagle.media_path}: {e}[/red]")
                try:
                    result.skipped.append(LizMediaSearchResult(
                        status=MediaStatus.SKIPPED,
                        media=LizMedia(eagle.media_path),
                        reason=f"Error loading media: {e}"
                    ))
                except ValueError:
                    pass
        return result


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
        self._result = searcher.search(eagletag)

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

    def printSkippedAsTable(self, sort_index: int = 0):
        if not self._result.skipped:
            print("[green]No media files were skipped.[/green]")
            return
            
        # Sort skipped list based on index
        sorted_results = self._sort_result_list(self._result.skipped, sort_index)

        table = Table(title=f"Skipped Media Files ({len(self._result.skipped)})")
        table.add_column("Filename", style="red", no_wrap=True)
        table.add_column("Creation Date", style="blue")
        table.add_column("Has EXIF", justify="center", style="magenta")
        table.add_column("Size (MB)", justify="right", style="green")
        table.add_column("Skip reason", style="white")

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
