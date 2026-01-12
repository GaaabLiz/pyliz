from typing import List, Optional
import os
import re
from pathlib import Path
import typer
from rich import print

from pylizlib.eaglecool.reader import EagleMediaReader
from pylizlib.media import media_app
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
    typer.echo(f"📁 Source: {path}")
    typer.echo(f"📁 Output: {output}")
    typer.echo("\n")
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
    media_global: List[LizMedia] = __search_media(path, eaglecatalog, eagletag, exclude, dry)
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

    __organize_files(media_global)




def __search_media(path: str, eaglecatalog: bool, eagletag: Optional[List[str]], exclude, dry: bool) -> List[LizMedia]:
    media_global: List[LizMedia] = []

    if not eaglecatalog:

        exclude_regex = None
        if exclude:
            try:
                exclude_regex = re.compile(exclude)
            except re.error as e:
                print(f"Error compiling regex '{exclude}': {e}")
                raise typer.Exit(code=1)

        print(f"Scanning directory: {path} ...")
        for root, _, files in os.walk(path):
            for file in files:
                # Check exclude pattern
                if exclude_regex and exclude_regex.search(file):
                    if dry:
                        print(f"  Skipping (regex match): {file}")
                    continue

                try:
                    media_global.append(LizMedia(Path(root) / file))
                except ValueError:
                    # Not a media file, skip silently or log if needed
                    pass
    else:
        skipped_media = []
        reader = EagleMediaReader(Path(path))
        eagles = reader.run()
        for eagle in eagles:
            try:
                if eagletag:
                    if not eagle.metadata:
                        print("[yellow]Warning: Eagle media without metadata, skipping tag filter.[/yellow]")
                        skipped_media.append(eagle.media_path)
                        continue
                    if not any(tag in eagle.metadata.tags for tag in eagletag):
                        print(f"[cyan]Eagle media {eagle.metadata.name} does not match specified tags, skipping.[/cyan]")
                        continue
                lizmedia = LizMedia(eagle.media_path)
                lizmedia.attach_eagle_metadata(eagle.metadata)
                media_global.append(lizmedia)
                print(f"[green]Added Eagle media: {eagle.media_path}[/green]")
            except ValueError as e:
                print(f"[red]Error: {eagle.media_path}: {e}[/red]")
                pass

        if skipped_media:
            print("\n")
            print(f"[yellow]Skipped {len(skipped_media)} Eagle media due to missing metadata or tag mismatch.[/yellow]")

    return media_global


def __organize_files(media: list[LizMedia]):
    pass