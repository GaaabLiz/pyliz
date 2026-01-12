import hashlib
import logging
import shutil
from typing import List, Optional
import os
import re
from pathlib import Path
import typer
from rich import print
from tqdm import tqdm

from pylizlib.eaglecool.reader import EagleMediaReader
from pylizlib.media import media_app
from pylizlib.media.compute.searcher import MediaSearcher
from pylizlib.media.lizmedia2 import LizMedia


@media_app.command()
def organizer(
        path: str = typer.Argument(
            ...,
            dir_okay=True,
            readable=True,
            help="Source path of files to organize"
        ),
        output: str = typer.Argument(
            ...,
            dir_okay=True,
            writable=True,
            readable=True,
            help="Destination path for organized files"
        ),
        eaglecatalog: bool = typer.Option(
            False,
            "--eaglecatalog",
            help="Import metadata from Eagle catalog"
        ),
        eagletag: Optional[List[str]] = typer.Option(
            None,
            "--eagletag", "-et",
            help="Eagle tags to apply (can be repeated: -et tag1 -et tag2)"
        ),
        xmp: bool = typer.Option(
            False,
            "--xmp",
            help="Generate XMP files for metadata"
        ),
        dry: bool = typer.Option(
            False,
            "--dry",
            help="Run in dry-run mode (preview only)"
        ),
        exclude: str = typer.Option(
            None,
            "--exclude", "-ex",
            help="Regex pattern to exclude files (-ex '.*\\.tmp' -ex '.*\\.temp')"
        ),
):
    """
    Organize files in the filesystem by applying metadata and filters.

    Supports Eagle metadata, XMP, and regex patterns for file exclusion.
    """

    # Basic validations
    if not path:
        typer.echo("❌ Error: path cannot be empty", err=True)
        raise typer.Exit(code=1)
    if not output:
        typer.echo("❌ Error: output cannot be empty", err=True)
        raise typer.Exit(code=1)

    # Log parameters
    typer.echo("\n")
    typer.echo(f"📁 Source: {path}")
    typer.echo(f"📁 Output: {output}")
    if dry:
        typer.echo("🔍 Running in DRY-RUN mode")
    if eaglecatalog:
        typer.echo("🦅 Eagle Catalog: enabled")
    if eagletag:
        typer.echo(f"🏷️  Eagle Tags: {', '.join(eagletag)}")
    if xmp:
        typer.echo("📝 XMP Metadata writing enabled")
    if exclude:
        typer.echo(f"🚫 Exclude pattern: {exclude})")

    # Searching file to organize
    searcher = MediaSearcher(path)
    if eaglecatalog:
        media_global: List[LizMedia] = searcher.search_eagle_catalog(eagletag)
    else:
        media_global: List[LizMedia] = searcher.search_file_system(exclude, dry)
    print("\n")
    print(f"Found {len(media_global)} files to process.")
    print("\n\n")
    if not media_global:
        print("No files to process. Exiting.")
        raise typer.Exit(code=0)

    # Organizing files
    no_progress: bool = False
    daily: bool = False
    copy: bool = True
    no_year: bool = False
    delete_duplicates: bool = False
    exif: bool = True

    __organize_files(media_global, output, no_progress=no_progress, daily=daily, copy=copy,
                     no_year=no_year, delete_duplicates=delete_duplicates, dry_run=dry, exif=exif)


def _sanitize_path(path: str) -> str:
    """Sanitize path to prevent path traversal attacks."""
    sanitized = os.path.normpath(path)
    # Check for dangerous path components
    if re.search(r'(\.\./|^\.\./|^\.\.)', sanitized):
        raise ValueError("Path contains invalid traversal components")
    return sanitized


def _ensure_directory_exists(folder_path):
    """
    Ensure the given folder path exists. If not, create all missing directories.

    Parameters:
    folder_path (str): The path to the folder.
    """
    os.makedirs(folder_path, exist_ok=True)
    # logging.debug(f"Ensured directory exists: {folder_path}")


def _get_file_hash(file_path: str, max_size: int = 100 * 1024 * 1024) -> str | None:
    """Get MD5 hash of file (for quick duplicate checks)."""
    try:
        # Skip large files (100MB+) to avoid excessive I/O
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


def __organize_files(media_list: list[LizMedia], target: str, *, no_progress: bool = False, daily: bool = False,
                     copy: bool = False,
                     no_year: bool = False, delete_duplicates: bool = False, dry_run: bool = False,
                     exif: bool = False, ) -> tuple[
    int, list[str]]:
    """
    Organise files from *source* into *target* according to the
    provided options.

    Parameters
    ----------
    media_list: list[LizMedia]
        Files to process.
    target : str
        Directories for output.
    no_progress : bool
        Disable progress bar for usage in a fully automated environment.
    daily : bool
        Create a day folder under month (i.e. YYYY/MM/DD).
    copy : bool
        Copy instead of moving files.
    no_year : bool
        Omit the year level (YYYY‑MM) instead of YYYY/MM.
    delete_duplicates : bool
        Delete source file when an identical target exists.
    dry_run : bool
        Skip all filesystem writes – useful for testing.
    exif : bool
        Prefer EXIF dates over file system timestamps.

    Returns
    -------
    tuple[int, list[str]]
        ``(success_count, failed_files)``
    """
    failed_files = []  # Track files that couldn't be processed
    success_count = 0

    if dry_run:
        print("[yellow]Dry run mode enabled - no actual file operations will be performed[/yellow]")

    # Precompute directory structure for progress reporting
    directory_counts = {}
    for media_item in media_list:
        file_path = str(media_item.path)
        try:
            sanitized_path = _sanitize_path(file_path)
        except ValueError:
            print(f"[yellow]Skipped invalid path: {file_path}[/yellow]")
            continue

        if exif and media_item.is_image:
            creation_date = media_item.creation_date_from_exif_or_file
            year, month, day = creation_date.year, creation_date.month, creation_date.day
        else:
            year, month, day = media_item.year, media_item.month, media_item.day

        folder_path = os.path.join(target, f"{year}", f"{month:02d}", f"{day:02d}")
        directory_counts[folder_path] = directory_counts.get(folder_path, 0) + 1

    # Process files with improved duplicate checking
    if no_progress:
        file_iter = media_list
    else:
        file_iter = tqdm(media_list, unit="files", desc="Organizing")

    for media_item in file_iter:
        file_path = str(media_item.path)
        # Sanitize path to prevent traversal attacks
        try:
            sanitized_path = _sanitize_path(file_path)
        except ValueError:
            print(f"[yellow]Skipped invalid path: {file_path}[/yellow]")
            continue

        if exif and media_item.is_image:
            creation_date = media_item.creation_date_from_exif_or_file
            year, month, day = creation_date.year, creation_date.month, creation_date.day
            original_timestamp = creation_date.timestamp()
        else:
            year, month, day = media_item.year, media_item.month, media_item.day
            original_timestamp = media_item.creation_time.timestamp()

        # Build target structure (with sanitization)
        folder_parts = [target]
        if no_year:
            folder_parts.append(f"{str(year)}-{month:02d}")
        else:
            folder_parts.append(str(year))
            folder_parts.append(f"{month:02d}")
        if daily:
            folder_parts.append(f"{day:02d}")
        target_folder = os.path.join(*folder_parts)
        if not dry_run:
            _ensure_directory_exists(target_folder)
        target_path = os.path.join(target_folder, os.path.basename(sanitized_path))

        # Check for duplicate (using hash first)
        if os.path.exists(target_path):
            # Check hash first (for large files)
            source_hash = _get_file_hash(file_path)
            target_hash = _get_file_hash(target_path)

            if source_hash == target_hash:
                # Exact match - handle as duplicate
                if delete_duplicates:
                    try:
                        if not dry_run:
                            os.remove(file_path)
                        print(f"[cyan]Deleted duplicate '{file_path}' (matches existing)[/cyan]")
                    except Exception as e:
                        print(f"[red]Error deleting duplicate '{file_path}': {e}[/red]")
                        failed_files.append(file_path)
                else:
                    print(f"[cyan]Skipping '{file_path}': Identical file already exists[/cyan]")
                continue
            else:
                # Different content but same path - error
                print(f"[red]File conflict: '{target_path}' already exists but is different[/red]")
                failed_files.append(file_path)
                continue

        # Move or copy (with permission checks)
        try:
            if not dry_run:
                if not os.access(target_folder, os.W_OK):
                    raise PermissionError(f"Write permission denied for {target_folder}")

                if copy:
                    # Use copy2 with permission preservation
                    shutil.copy2(file_path, target_path)
                else:
                    # Check write permissions before moving
                    shutil.move(file_path, target_path)

                # Explicitly set the modification time to the original creation time
                # This ensures the file appears with the correct "date" in file explorers
                os.utime(target_path, (original_timestamp, original_timestamp))

            # Update progress counts
            success_count += 1
            if not no_progress:
                # If tqdm is active, we avoid too much printing to not break the bar,
                # or we can use tqdm.write if we really want logging.
                pass
            else:
                print(f"Processed {file_path} -> {target_path}")

        except Exception as e:
            print(f"[red]Error processing {file_path}: {e}[/red]")
            failed_files.append(file_path)
        finally:
            # Update directory counts for progress reporting
            if not no_progress and os.path.exists(target_path):
                directory_counts[target_folder] = directory_counts.get(target_folder, 0) + 1

    # Show progress summary
    if file_iter and not no_progress:
        # file_iter is a tqdm instance here
        file_iter.close()
    print(f"Organized {success_count} files")

    return success_count, failed_files

