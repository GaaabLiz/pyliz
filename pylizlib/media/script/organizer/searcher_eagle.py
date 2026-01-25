import time
from pathlib import Path
from typing import List, Optional

from rich import print
from tqdm import tqdm

from pylizlib.core.domain.os import FileType
from pylizlib.eaglecool.reader import EagleCoolReader
from pylizlib.media.lizmedia import LizMedia, MediaListResult, LizMediaSearchResult, MediaStatus


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
