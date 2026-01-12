import hashlib
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from rich import print
from tqdm import tqdm

from pylizlib.media.lizmedia2 import LizMedia


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

    def __init__(self, media_list: list[LizMedia], target: str):
        self.media_list = media_list
        self.target = target

    def organize(self, options: OrganizerOptions) -> tuple[int, list[str]]:
        """
        Organize files from *source* into *target* according to the provided options.

        Returns:
            tuple[int, list[str]]: (success_count, failed_files)
        """
        failed_files = []
        success_count = 0

        if options.dry_run:
            print("[yellow]Dry run mode enabled - no actual file operations will be performed[/yellow]")

        # Prepare iteration
        file_iter = self.media_list if options.no_progress else tqdm(self.media_list, unit="files", desc="Organizing")

        for media_item in file_iter:
            file_path = str(media_item.path)

            try:
                sanitized_path = self._sanitize_path(file_path)
            except ValueError:
                print(f"[yellow]Skipped invalid path: {file_path}[/yellow]")
                continue

            # Determine date and original timestamp
            if options.exif and media_item.is_image:
                creation_date = media_item.creation_date_from_exif_or_file
                year, month, day = creation_date.year, creation_date.month, creation_date.day
                original_timestamp = creation_date.timestamp()
            else:
                year, month, day = media_item.year, media_item.month, media_item.day
                original_timestamp = media_item.creation_time.timestamp()

            # Build target path
            target_folder = self._build_target_folder_path(self.target, year, month, day, options.no_year, options.daily)
            target_path = os.path.join(target_folder, os.path.basename(sanitized_path))

            if not options.dry_run:
                self._ensure_directory_exists(target_folder)

            # Handle existing files (duplicates/conflicts)
            if os.path.exists(target_path):
                if self._handle_existing_file(file_path, target_path, options.delete_duplicates, options.dry_run):
                     # Continue means we skipped or deleted, so we move to next file
                     # If handle_existing_file returns True, it means "skip/handled", continue loop
                     continue
                else:
                    # If returns False, it means conflict error
                    failed_files.append(file_path)
                    continue

            # Execute move or copy
            if self._execute_transfer(file_path, target_path, target_folder, options.copy, options.dry_run, original_timestamp):
                success_count += 1
                if options.no_progress:
                     print(f"Processed {file_path} -> {target_path}")
            else:
                failed_files.append(file_path)

        # Cleanup progress bar
        if not options.no_progress and hasattr(file_iter, "close"):
            file_iter.close()

        print(f"Organized {success_count} files")
        return success_count, failed_files

    def _build_target_folder_path(self, base_target: str, year: int, month: int, day: int,
                                  no_year: bool, daily: bool) -> str:
        """Constructs the target folder path based on date options."""
        folder_parts = [base_target]
        if no_year:
            folder_parts.append(f"{str(year)}-{month:02d}")
        else:
            folder_parts.append(str(year))
            folder_parts.append(f"{month:02d}")
        if daily:
            folder_parts.append(f"{day:02d}")
        return os.path.join(*folder_parts)

    def _handle_existing_file(self, source_path: str, target_path: str,
                              delete_duplicates: bool, dry_run: bool) -> bool:
        """
        Checks if file exists and handles duplicates.
        Returns True if the file loop should continue (skipped or deleted),
        False if it's a conflict/error that should be logged as failure.
        """
        source_hash = self._get_file_hash(source_path)
        target_hash = self._get_file_hash(target_path)

        if source_hash == target_hash:
            # Exact match - handle as duplicate
            if delete_duplicates:
                try:
                    if not dry_run:
                        os.remove(source_path)
                    print(f"[cyan]Deleted duplicate '{source_path}' (matches existing)[/cyan]")
                except Exception as e:
                    print(f"[red]Error deleting duplicate '{source_path}': {e}[/red]")
                    # Return False to treat as failure because we couldn't delete as requested
                    # But technically we might want to just skip?
                    # The original logic appended to failed_files if delete failed.
                    return False 
            else:
                print(f"[cyan]Skipping '{source_path}': Identical file already exists[/cyan]")
            return True
        else:
            # Different content but same path - error
            print(f"[red]File conflict: '{target_path}' already exists but is different[/red]")
            return False

    def _execute_transfer(self, source_path: str, target_path: str, target_folder: str,
                          copy: bool, dry_run: bool, original_timestamp: float) -> bool:
        """
        Moves or copies the file and restores timestamps.
        Returns True on success, False on error.
        """
        try:
            if not dry_run:
                if not os.access(target_folder, os.W_OK):
                    raise PermissionError(f"Write permission denied for {target_folder}")

                if copy:
                    shutil.copy2(source_path, target_path)
                else:
                    shutil.move(source_path, target_path)

                # Explicitly set the modification time to the original creation time
                os.utime(target_path, (original_timestamp, original_timestamp))
            return True
        except Exception as e:
            print(f"[red]Error processing {source_path}: {e}[/red]")
            return False

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
        except Exception as e:
            print(f"[red]Error hashing {file_path}: {e}[/red]")
            return None