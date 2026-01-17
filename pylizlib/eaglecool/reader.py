import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Generator, List, Optional

from rich import print
from tqdm import tqdm
from pylizlib.eaglecool.model.metadata import Metadata


class EagleMedia:
    def __init__(self, media_path: Path, metadata: Metadata):
        self.media_path = media_path
        self.metadata = metadata


class EagleMediaReader:
    def __init__(self, catalogue: Path):
        self.catalogue = catalogue
        self.media_found: List[EagleMedia] = []
        self.error_paths: List[Path] = []
        self.scanned_folders_count: int = 0

    def run(self):
        images_dir = self.catalogue / "images"

        if not images_dir.exists():
            raise ValueError(f"Eagle catalogue 'images' directory not found: {images_dir}")

        folders = list(images_dir.iterdir())
        for folder in tqdm(folders, desc="Scanning Eagle Library folders", unit="folders"):
            if folder.is_dir():
                self.scanned_folders_count += 1
                result = self.__handle_eagle_folder(folder)
                if result:
                    self.media_found.append(result)

    def __handle_eagle_folder(self, folder: Path) -> Optional[EagleMedia]:
        metadata_obj = None
        media_file = None

        for file_path in folder.iterdir():
            if not file_path.is_file():
                continue

            if "_thumbnail" in file_path.name:
                continue

            if file_path.name == "metadata.json":
                try:
                    with file_path.open('r', encoding='utf-8') as f:
                        data = json.load(f)
                        metadata_obj = Metadata.from_json(data)
                except Exception as e:
                    print(f"[red]Error reading metadata from {file_path}: {e}[/red]")
                    self.error_paths.append(folder)
                    return None
            else:
                # Assuming any other file that is not a thumbnail and not metadata.json is the media file
                media_file = file_path

        # Requirement: every valid media must have a media file and its metadata.json
        if metadata_obj and media_file:
            return EagleMedia(media_file, metadata_obj)
        
        # If media file or metadata.json is missing, it's an error
        self.error_paths.append(folder)
        return None
