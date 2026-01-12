import os
import re
from pathlib import Path
from typing import List, Optional

import typer
from rich import print

from pylizlib.eaglecool.reader import EagleMediaReader
from pylizlib.media.lizmedia2 import LizMedia


class MediaSearcher:
    """
    Utility class to search for media files in a directory, optionally integrating with Eagle library
    or filtering by regex.
    """

    def __init__(self, path: str):
        self.path = path

    def search_file_system(self, exclude: str = None, dry: bool = False) -> List[LizMedia]:
        media_global: List[LizMedia] = []
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
                if exclude_regex and exclude_regex.search(file):
                    if dry:
                        print(f"  Skipping (regex match): {file}")
                    continue

                try:
                    media_global.append(LizMedia(Path(root) / file))
                except ValueError:
                    # Not a media file, skip silently or log if needed
                    pass
        return media_global

    def search_eagle_catalog(self, eagletag: Optional[List[str]] = None) -> List[LizMedia]:
        media_global: List[LizMedia] = []
        skipped_media = []
        reader = EagleMediaReader(Path(self.path))
        eagles = reader.run()

        for eagle in eagles:
            try:
                if eagletag:
                    if not eagle.metadata:
                        print("[yellow]Warning: Eagle media without metadata, skipping tag filter.[/yellow]")
                        skipped_media.append(eagle.media_path)
                        continue
                    if not any(tag in eagle.metadata.tags for tag in eagletag):
                        print(f"[cyan]Eagle media {eagle.metadata.name} does not match specified tags, skipping.[/cyan]")
                        continue

                lizmedia = LizMedia(eagle.media_path)
                lizmedia.attach_eagle_metadata(eagle.metadata)
                media_global.append(lizmedia)
                print(f"[green]Added Eagle media: {eagle.media_path}[/green]")
            except ValueError as e:
                print(f"[red]Error: {eagle.media_path}: {e}[/red]")
                pass

        if skipped_media:
            print("\n")
            print(f"[yellow]Skipped {len(skipped_media)} Eagle media due to missing metadata or tag mismatch.[/yellow]")

        return media_global
