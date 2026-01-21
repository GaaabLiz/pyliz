from pathlib import Path
from typing import List, Optional
import os
import typer
from rich import print
from rich.console import Console
from rich.table import Table

from pylizlib.media import media_app
from pylizlib.media.compute.organizer import MediaOrganizer, OrganizerOptions, OrganizerResult
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
        list_errored: bool = typer.Option(
            False,
            "--list-errored", "-lerr",
            help="List errored files during search."
        ),
        list_accepted_order_index: int = typer.Option(
            0,
            "--list-accepted-order-index", "-laoi",
            help="Index of the column to sort accepted list by (0-4). Default is 0 (Filename). Columns: 0=Filename, 1=Creation Date, 2=Has EXIF, 3=Extension, 4=Size.",
            min=0,
            max=4
        ),
        list_rejected_order_index: int = typer.Option(
            0,
            "--list-rejected-order-index", "-lroi",
            help="Index of the column to sort rejected list by (0-4). Default is 0 (Filename). Sort Keys: 0=Filename, 1=Creation Date, 2=Has EXIF, 3=Extension, 4=Size. (Note: Extension is not shown in rejected table)",
            min=0,
            max=4
        ),
        list_errored_order_index: int = typer.Option(
            0,
            "--list-errored-order-index", "-leoi",
            help="Index of the column to sort errored list by (0-4). Default is 0 (Filename). Sort Keys: 0=Filename, 1=Creation Date, 2=Has EXIF, 3=Extension, 4=Size.",
            min=0,
            max=4
        ),
        print_results: bool = typer.Option(
            False,
            "--print-results", "-pres",
            help="Print organization results in a table."
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
    typer.echo("\n" + "─" * 50)
    typer.echo(f"📁 Source: {path}")
    typer.echo(f"📁 Output: {output}")
    typer.echo(f"🔍 Dry-run: {'Yes' if dry else 'No'}")
    typer.echo(f"🦅 Eagle Catalog: {'Yes' if eaglecatalog else 'No'}")
    if eaglecatalog:
        typer.echo(f"🏷️  Eagle Tags: {', '.join(eagletag) if eagletag else 'None'}")
    typer.echo(f"📝 XMP Metadata: {'Yes' if xmp else 'No'}")
    typer.echo(f"🚫 Exclude pattern: {exclude if exclude else 'None'}")
    typer.echo(f"✅ List accepted: {'Yes' if list_accepted else 'No'}")
    typer.echo(f"❌ List rejected: {'Yes' if list_rejected else 'No'}")
    typer.echo(f"⚠️ List errored: {'Yes' if list_errored else 'No'}")
    typer.echo(f"📊 Print results: {'Yes' if print_results else 'No'}")
    
    column_names = ["Filename", "Creation Date", "Has EXIF", "Extension", "Size"]
    sort_col_acc = column_names[list_accepted_order_index]
    sort_col_rej = column_names[list_rejected_order_index]
    sort_col_err = column_names[list_errored_order_index]
    typer.echo(f"🔢 Accepted list sort: {sort_col_acc} (index {list_accepted_order_index})")
    typer.echo(f"🔢 Rejected list sort: {sort_col_rej} (index {list_rejected_order_index})")
    typer.echo(f"🔢 Errored list sort: {sort_col_err} (index {list_errored_order_index})")
    typer.echo("─" * 50 + "\n")

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
    if list_accepted:
        with Console().status("[bold cyan]Generating Accepted Table...[/bold cyan]"):
            searcher.printAcceptedAsTable(list_accepted_order_index)
            
    print("\n")
    if list_rejected:
        with Console().status("[bold cyan]Generating Rejected Table...[/bold cyan]"):
            searcher.printRejectedAsTable(list_rejected_order_index)
            
    print("\n")
    if list_errored:
        with Console().status("[bold cyan]Generating Errored Table...[/bold cyan]"):
            searcher.printErroredAsTable(list_errored_order_index)
    print("\n\n")

    # Check if there are files to process
    if not media_global:
        print("No files to process. Exiting.")
        raise typer.Exit(code=0)

    # Wait for user confirmation
    # input("Press Enter to continue with organization...")

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

    # Pass LizMediaSearchResult objects directly to MediaOrganizer to preserve sidecar info
    results = MediaOrganizer(media_global, output, options).organize()

    if print_results:
        with Console().status("[bold cyan]Generating Results Table...[/bold cyan]"):
            print("\n")
            table = Table(title=f"Organization Results ({len(results)})")
            table.add_column("Status", justify="center")
            table.add_column("Filename", style="cyan")
            table.add_column("Extension", style="yellow", justify="center")
            table.add_column("Destination", style="magenta", overflow="fold")
            table.add_column("Reason", style="white", overflow="fold")

            for res in results:
                status = "[green]Success[/green]" if res.success else "[red]Failed[/red]"
                
                # Show path relative to the parent of the output directory for better readability
                if res.destination_path:
                    dest = os.path.relpath(res.destination_path, Path(output).parent)
                else:
                    dest = "N/A"
                    
                table.add_row(status, res.source_file.name, res.source_file.suffix.lower(), dest, res.reason)
            
            Console().print(table)
            print("\n")

