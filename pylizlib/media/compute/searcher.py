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
from pylizlib.media.lizmedia import LizMedia, MediaListResult, LizMediaSearchResult, MediaStatus
from pylizlib.media.view.table import MediaListResultPrinter


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
        printer = MediaListResultPrinter(self._result)
        printer.print_accepted(sort_index)

    def printRejectedAsTable(self, sort_index: int = 0):
        printer = MediaListResultPrinter(self._result)
        printer.print_rejected(sort_index)

    def printErroredAsTable(self, sort_index: int = 0):
        printer = MediaListResultPrinter(self._result)
        printer.print_errored(sort_index)
