import os
import re
from pathlib import Path
from typing import List, Optional

import typer
from rich import print
from rich.console import Console
from rich.table import Table

from pylizlib.eaglecool.reader import EagleMediaReader
from pylizlib.media.lizmedia2 import LizMedia, MediaListResult


class MediaSearcher:
    """
    Utility class to search for media files in a directory, optionally integrating with Eagle library
    or filtering by regex.
    """

    def __init__(self, path: str):
        self.path = path
        self._result = MediaListResult()
        self._console = Console()

    def get_result(self) -> MediaListResult:
        return self._result

    def run_search_system(self, exclude: str = None, dry: bool = False):
        self._result = MediaListResult()  # Reset result
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
                # Check exclude pattern
                file_path = Path(root) / file
                if exclude_regex and exclude_regex.search(file):
                    if dry:
                        print(f"  Skipping (regex match): {file}")
                    try:
                        self._result.skipped.append(LizMedia(file_path))
                    except ValueError:
                        pass
                    continue

                try:
                    self._result.media_list.append(LizMedia(file_path))
                except ValueError:
                    # Not a media file, skip silently or log if needed
                    pass

    def run_search_eagle(self, eagletag: Optional[List[str]] = None):
        self._result = MediaListResult()  # Reset result
        reader = EagleMediaReader(Path(self.path))
        eagles = reader.run()

        for eagle in eagles:
            try:
                if eagletag:
                    if not eagle.metadata:
                        print("[yellow]Warning: Eagle media without metadata, skipping tag filter.[/yellow]")
                        try:
                            self._result.skipped.append(LizMedia(eagle.media_path))
                        except ValueError:
                            pass
                        continue
                    if not any(tag in eagle.metadata.tags for tag in eagletag):
                        print(f"[cyan]Eagle media {eagle.metadata.name} does not match specified tags, skipping.[/cyan]")
                        try:
                            self._result.skipped.append(LizMedia(eagle.media_path))
                        except ValueError:
                            pass
                        continue

                lizmedia = LizMedia(eagle.media_path)
                lizmedia.attach_eagle_metadata(eagle.metadata)
                self._result.media_list.append(lizmedia)
                print(f"[green]Added Eagle media: {eagle.media_path}[/green]")
            except ValueError as e:
                print(f"[red]Error: {eagle.media_path}: {e}[/red]")
                try:
                    self._result.skipped.append(LizMedia(eagle.media_path))
                except ValueError:
                    pass

    def printAcceptedAsTable(self):
        if not self._result.media_list:
            print("[yellow]No accepted media files found.[/yellow]")
            return

        table = Table(title=f"Accepted Media Files ({len(self._result.media_list)})")
        table.add_column("Filename", style="cyan", no_wrap=True)
        table.add_column("Path", style="magenta")
        table.add_column("Size (MB)", justify="right", style="green")
        table.add_column("Date", justify="right", style="blue")

        for media in self._result.media_list:
            table.add_row(
                media.file_name,
                str(media.path),
                f"{media.size_mb:.2f}",
                media.creation_time.strftime("%Y-%m-%d %H:%M:%S")
            )

        self._console.print(table)

    def printSkippedAsTable(self):
        if not self._result.skipped:
            print("[green]No media files were skipped.[/green]")
            return

        table = Table(title=f"Skipped Media Files ({len(self._result.skipped)})")
        table.add_column("Filename", style="red", no_wrap=True)
        table.add_column("Path", style="magenta")

        for media in self._result.skipped:
            table.add_row(
                media.file_name,
                str(media.path)
            )

        self._console.print(table)