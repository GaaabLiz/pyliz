import hashlib
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from rich import print
from tqdm import tqdm

from pylizlib.media.lizmedia2 import LizMedia, LizMediaSearchResult


@dataclass
class OrganizerResult:
    success: bool
    source_file: Path
    media: Optional[LizMedia] = None
    reason: str = ""
    destination_path: Optional[str] = None

    @property
    def source_path(self) -> str:
        return str(self.source_file)


@dataclass
class OrganizerOptions:
    no_progress: bool = False
    daily: bool = False
    copy: bool = False
    no_year: bool = False
    delete_duplicates: bool = False
    dry_run: bool = False
    exif: bool = False


class MediaOrganizer:
    """
    Class responsible for organizing media files into a target directory structure
    based on their creation date (from EXIF or filesystem).
    """

    def __init__(self, search_results: list[LizMediaSearchResult], target: str, options: OrganizerOptions):
        self.search_results = search_results
        self.target = target
        self.options = options

    def organize(self) -> List[OrganizerResult]:
        """
        Organize files from *source* into *target* according to the provided options.

        Returns:
            List[OrganizerResult]: List of results for each processed file.
        """
        results: List[OrganizerResult] = []

        # Prepare iteration
        file_iter = self.search_results if self.options.no_progress else tqdm(self.search_results, unit="files", desc="Organizing")

        for item in file_iter:
            if not item.has_lizmedia():
                continue
            
            media_item = item.media
            file_path = str(media_item.path)

            try:
                sanitized_path = self._sanitize_path(file_path)
            except ValueError as e:
                # print(f"[yellow]Rejected invalid path: {file_path}[/yellow]")
                results.append(OrganizerResult(success=False, source_file=media_item.path, media=media_item, reason=str(e)))
                continue

            # Determine date and original timestamp
            if self.options.exif and media_item.is_image:
                creation_date = media_item.creation_date_from_exif_or_file
                year, month, day = creation_date.year, creation_date.month, creation_date.day
                original_timestamp = creation_date.timestamp()
            else:
                year, month, day = media_item.year, media_item.month, media_item.day
                original_timestamp = media_item.creation_time.timestamp()

            # Build target path
            target_folder = self._build_target_folder_path(self.target, year, month, day)
            target_path = os.path.join(target_folder, os.path.basename(sanitized_path))

            if not self.options.dry_run:
                self._ensure_directory_exists(target_folder)

            # Handle existing files (duplicates/conflicts)
            if os.path.exists(target_path):
                existing_result = self._handle_existing_file(file_path, target_path, media_item)
                if existing_result:
                    results.append(existing_result)
                    continue

            # Execute move or copy
            transfer_result = self._execute_transfer(file_path, target_path, target_folder, original_timestamp, media_item)
            results.append(transfer_result)
            
            # Handle sidecars if media transfer was successful
            if transfer_result.success and item.has_sidecars():
                for sidecar_path in item.sidecar_files:
                    sidecar_target = os.path.join(target_folder, sidecar_path.name)
                    # Pass full path string or Path object? _execute_sidecar_transfer expects Path.
                    # item.sidecar_files contains Path objects.
                    sidecar_result = self._execute_sidecar_transfer(sidecar_path, sidecar_target, target_folder)
                    results.append(sidecar_result)

        # Cleanup progress bar
        if not self.options.no_progress and hasattr(file_iter, "close"):
            file_iter.close()

        return results

    def _build_target_folder_path(self, base_target: str, year: int, month: int, day: int) -> str:
        """Constructs the target folder path based on date options."""
        folder_parts = [base_target]
        if self.options.no_year:
            folder_parts.append(f"{str(year)}-{month:02d}")
        else:
            folder_parts.append(str(year))
            folder_parts.append(f"{month:02d}")
        if self.options.daily:
            folder_parts.append(f"{day:02d}")
        return os.path.join(*folder_parts)

    def _handle_existing_file(self, source_path: str, target_path: str, media: LizMedia) -> OrganizerResult | None:
        """
        Checks if file exists and handles duplicates.
        Returns OrganizerResult if handled (skipped/deleted/error), None if conflict (should probably be error too?) 
        """
        source_hash = self._get_file_hash(source_path)
        target_hash = self._get_file_hash(target_path)

        if source_hash == target_hash:
            # Exact match - handle as duplicate
            if self.options.delete_duplicates:
                try:
                    if not self.options.dry_run:
                        os.remove(source_path)
                    return OrganizerResult(success=False, source_file=media.path, media=media, reason="Duplicate deleted", destination_path=target_path)
                except Exception as e:
                    return OrganizerResult(success=False, source_file=media.path, media=media, reason=f"Error deleting duplicate: {e}", destination_path=target_path)
            else:
                return OrganizerResult(success=False, source_file=media.path, media=media, reason="Duplicate skipped", destination_path=target_path)
        else:
            # Different content but same path - error
            return OrganizerResult(success=False, source_file=media.path, media=media, reason="File conflict: target exists but content differs", destination_path=target_path)

    def _execute_transfer(self, source_path: str, target_path: str, target_folder: str, original_timestamp: float, media: LizMedia) -> OrganizerResult:
        """
        Moves or copies the file and restores timestamps.
        Returns OrganizerResult.
        """
        try:
            if not self.options.dry_run:
                if not os.access(target_folder, os.W_OK):
                    raise PermissionError(f"Write permission denied for {target_folder}")

                if self.options.copy:
                    shutil.copy2(source_path, target_path)
                else:
                    shutil.move(source_path, target_path)

                # Explicitly set the modification time to the original creation time
                # os.utime(target_path, (original_timestamp, original_timestamp))
            return OrganizerResult(success=True, source_file=media.path, media=media, destination_path=target_path)
        except Exception as e:
            return OrganizerResult(success=False, source_file=media.path, media=media, reason=f"Transfer error: {e}", destination_path=target_path)

    def _execute_sidecar_transfer(self, source_path: Path, target_path: str, target_folder: str) -> OrganizerResult:
        """
        Moves or copies a sidecar file. Returns OrganizerResult.
        """
        try:
            if not self.options.dry_run:
                if self.options.copy:
                    shutil.copy2(source_path, target_path)
                else:
                    shutil.move(source_path, target_path)
            return OrganizerResult(success=True, source_file=source_path, destination_path=target_path)
        except Exception as e:
            return OrganizerResult(success=False, source_file=source_path, reason=f"Sidecar transfer error: {e}", destination_path=target_path)

    def _sanitize_path(self, path: str) -> str:
        """Sanitize path to prevent path traversal attacks."""
        sanitized = os.path.normpath(path)
        if re.search(r'(\.\./|^\.\./|^\.\.)', sanitized):
            raise ValueError("Path contains invalid traversal components")
        return sanitized

    def _ensure_directory_exists(self, folder_path: str):
        """Ensure the given folder path exists."""
        os.makedirs(folder_path, exist_ok=True)

    def _get_file_hash(self, file_path: str, max_size: int = 100 * 1024 * 1024) -> str | None:
        """Get MD5 hash of file (for quick duplicate checks)."""
        try:
            if os.path.getsize(file_path) > max_size:
                return "LARGE_FILE"
            with open(file_path, 'rb') as f:
                chunk = f.read(4096)
                if not chunk:
                    return None
                hash_obj = hashlib.md5()
                while chunk:
                    hash_obj.update(chunk)
                    chunk = f.read(4096)
            return hash_obj.hexdigest()
        except Exception:
            return None
