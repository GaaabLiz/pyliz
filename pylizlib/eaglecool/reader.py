import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Generator, List, Optional, Tuple

from rich import print
from tqdm import tqdm
from pylizlib.core.domain.os import FileType
from pylizlib.core.os.file import is_media_file
from pylizlib.eaglecool.model.metadata import Metadata


class EagleItem:
    def __init__(self, file_path: Path, metadata: Metadata):
        self.file_path = file_path
        self.metadata = metadata


class EagleCoolReader:
    def __init__(self, catalogue: Path, include_deleted: bool = False, file_types: List[FileType] = None):
        self.catalogue = catalogue
        self.include_deleted = include_deleted
        self.file_types = file_types if file_types else [FileType.IMAGE, FileType.VIDEO, FileType.AUDIO]
        self.items: List[EagleItem] = []
        self.error_paths: List[Tuple[Path, str]] = []
        self.skipped_path: List[Tuple[Path, str]] = []
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
                    self.items.append(result)

    def __handle_eagle_folder(self, folder: Path) -> Optional[EagleItem]:
        metadata_obj, media_file, error_occurred = self.__scan_folder_contents(folder)

        if error_occurred:
            return None

        # Check missing components
        if not metadata_obj or not media_file:
            reason = []
            if not metadata_obj:
                reason.append("Missing metadata.json")
            if not media_file:
                reason.append("Missing media file")
            self.error_paths.append((folder, ", ".join(reason)))
            return None

        # Check for deleted items
        if metadata_obj.isDeleted and not self.include_deleted:
            self.skipped_path.append((media_file, "Item is deleted"))
            return None

        # Check file type
        if is_media_file(str(media_file)):
            # TODO: Implement stricter checking based on self.file_types
            return EagleItem(media_file, metadata_obj)
        else:
            # TODO: Handle other file types
            self.skipped_path.append((media_file, f"Unsupported file type: {media_file.suffix}"))
            return None

    def __scan_folder_contents(self, folder: Path) -> Tuple[Optional[Metadata], Optional[Path], bool]:
        """
        Scans the folder to find the metadata file and the media file.
        Returns (Metadata object, Media file path, Error occurred flag).
        """
        metadata_obj = None
        media_file = None

        for file_path in folder.iterdir():
            if not file_path.is_file():
                continue

            if "_thumbnail" in file_path.name:
                continue

            if file_path.name == "metadata.json":
                metadata_obj = self.__load_metadata(file_path, folder)
                if metadata_obj is None:
                    return None, None, True
            else:
                media_file = file_path
        
        return metadata_obj, media_file, False

    def __load_metadata(self, file_path: Path, folder: Path) -> Optional[Metadata]:
        try:
            with file_path.open('r', encoding='utf-8') as f:
                data = json.load(f)
                return Metadata.from_json(data)
        except Exception as e:
            print(f"[red]Error reading metadata from {file_path}: {e}[/red]")
            self.error_paths.append((folder, f"Error reading metadata: {e}"))
            return None
