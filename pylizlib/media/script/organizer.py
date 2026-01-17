from typing import List, Optional
import os
import typer
from rich import print

from pylizlib.media import media_app
from pylizlib.media.compute.organizer import MediaOrganizer, OrganizerOptions
from pylizlib.media.compute.searcher import MediaSearcher
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
        list_rejected: bool = typer.Option(
            False,
            "--list-rejected", "-lrej",
            help="List rejected files during search."
        ),
        list_custom_order_index: int = typer.Option(
            0,
            "--list-custom-order-index", "-loi",
            help="Index of the column to sort by (0-4). Default is 0 (Filename). Columns: 0=Filename, 1=Creation Date, 2=Has EXIF, 3=Extension, 4=Size.",
            min=0,
            max=4
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
    if eaglecatalog:
        searcher.run_search_eagle(eagletag)
    else:
        searcher.run_search_system(exclude, dry)
    
    search_result = searcher.get_result()
    media_global = search_result.accepted

    # Logging search results
    print("\n")
    searcher.printAcceptedAsTable(list_custom_order_index) if list_accepted else None
    print("\n")
    searcher.printRejectedAsTable(list_custom_order_index) if list_rejected else None
    print("\n\n")

    if not media_global:
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

    # Extract LizMedia objects from LizMediaSearchResult for the organizer
    media_to_organize = [item.media for item in media_global]
    MediaOrganizer(media_to_organize, output, options).organize()

