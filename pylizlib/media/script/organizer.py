from typing import List, Optional
import os
import typer
from rich import print

from pylizlib.media import media_app
from pylizlib.media.compute.organizer import MediaOrganizer, OrganizerOptions
from pylizlib.media.compute.searcher import MediaSearcher, MediaSearcherResultLogger
from pylizlib.media.lizmedia2 import LizMedia, MediaListResult


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
        list_accepted: bool = typer.Option(
            False,
            "--list-accepted", "-lac",
            help="List accepted file during search."
        ),
        list_skipped: bool = typer.Option(
            False,
            "--list-skipped", "-lskip",
            help="List skipped files during search."
        )
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
    typer.echo("\n")

    # Searching file to organize
    searcher = MediaSearcher(path)
    search_result: MediaListResult = searcher.search_eagle_catalog(eagletag) if eaglecatalog else searcher.search_file_system(exclude, dry)

    # Print summary
    print("\n")
    print(f"Processed {search_result.total_count} files.")
    print(f"Found {len(search_result.media_list)} media files to organize.")
    print(f"Skipped {len(search_result.skipped)} files.")

    # Print detailed summary if requested
    result_logger = MediaSearcherResultLogger(search_result)
    if list_accepted and search_result.media_list:
        result_logger.printAcceptedAsTable()
    if list_skipped and search_result.skipped:
        result_logger.printSkippedAsTable()

    if search_result.skipped:
        input("")
    print("\n\n")

    if not search_result.media_list:
        print("No files to process. Exiting.")
        raise typer.Exit(code=0)

    # Organizing files
    options = OrganizerOptions(
        no_progress=False,
        daily=False,
        copy=True,
        no_year=False,
        delete_duplicates=False,
        dry_run=dry,
        exif=True
    )

    MediaOrganizer(search_result.media_list, output, options).organize()

