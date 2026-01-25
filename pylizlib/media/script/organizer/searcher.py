import os
import shutil
import tempfile
from pathlib import Path
from typing import List, Optional

from rich import print
from rich.console import Console
from rich.table import Table
from tqdm import tqdm

from pylizlib.media.lizmedia import MediaListResult
from pylizlib.media.view.table import MediaListResultPrinter
from pylizlib.media.script.organizer.searcher_os import FileSystemSearcher
from pylizlib.media.script.organizer.searcher_eagle import EagleCatalogSearcher
from pylizlib.media.util.metadata import MetadataHandler


class MediaSearcher:
    """
    Utility class to search for media files in a directory, optionally integrating with Eagle library
    or filtering by regex. Acts as a facade for specific search strategies.
    """

    def __init__(self, path: str):
        self.path = path
        self._result = MediaListResult()
        self._console = Console()
        self.generated_xmps_list: List[tuple[str, str]] = []
        self._temp_xmp_dir: Optional[str] = None

    def get_result(self) -> MediaListResult:
        return self._result

    def run_search_system(self, exclude: str = None, dry: bool = False):
        searcher = FileSystemSearcher(self.path)
        self._result = searcher.search(exclude, dry)

    def run_search_eagle(self, eagletag: Optional[List[str]] = None):
        searcher = EagleCatalogSearcher(self.path)
        searcher.search(eagletag)
        self._result = searcher.get_result()

    def printAcceptedAsTable(self, sort_index: int = 0):
        printer = MediaListResultPrinter(self._result)
        printer.print_accepted(sort_index)

    def printRejectedAsTable(self, sort_index: int = 0):
        printer = MediaListResultPrinter(self._result)
        printer.print_rejected(sort_index)

    def printErroredAsTable(self, sort_index: int = 0):
        printer = MediaListResultPrinter(self._result)
        printer.print_errored(sort_index)

    def generate_missing_xmps(self):
        """
        Generates missing XMP sidecar files for accepted media.
        """
        self.generated_xmps_list = []
        self._temp_xmp_dir = tempfile.mkdtemp(prefix="pyliz_xmp_")
        
        # Use tqdm for progress if there are items
        accepted_items = [i for i in self._result.accepted if i.media and not i.media.has_xmp_sidecar()]
        
        if not accepted_items:
             self._console.print("[green]No missing XMP files needed generation.[/green]\n")
             return

        for item in tqdm(accepted_items, desc="Generating missing XMPs", unit="files"):
            try:
                # Construct correct filename in temp dir
                media_path = Path(item.path)
                xmp_name = f"{media_path.stem}.xmp"
                temp_path = os.path.join(self._temp_xmp_dir, xmp_name)
                
                handler = MetadataHandler(item.path)
                if handler.generate_xmp(temp_path):
                    # Attach to LizMedia
                    item.media.attach_sidecar_file(Path(temp_path))
                    self.generated_xmps_list.append((item.media.file_name, temp_path))
                else:
                    self._console.print(f"[red]Failed to generate XMP for {item.media.file_name} (check logs/exiftool)[/red]")
                
            except Exception as e:
                self._console.print(f"[red]Error processing XMP for {item.media.file_name}: {e}[/red]")

        if self.generated_xmps_list:
            print("\n")
            table = Table(title=f"Generated Missing XMP Files ({len(self.generated_xmps_list)})")
            table.add_column("Media Filename", style="cyan")
            table.add_column("Generated XMP Path", style="magenta")
            
            for media_name, xmp_path in self.generated_xmps_list:
                table.add_row(media_name, xmp_path)
            
            self._console.print(table)
            print("\n")

    def cleanup_generated_xmps(self):
        """
        Deletes the temporary XMP files and the directory created.
        """
        if not self.generated_xmps_list:
            if self._temp_xmp_dir and os.path.exists(self._temp_xmp_dir):
                try:
                    shutil.rmtree(self._temp_xmp_dir)
                except OSError as e:
                    print(f"[red]Error removing temp dir {self._temp_xmp_dir}: {e}[/red]")
            return

        print("\n")
        with tqdm(self.generated_xmps_list, desc="Cleaning up temp XMP files", unit="files") as pbar:
            for _, xmp_path in pbar:
                try:
                    if os.path.exists(xmp_path):
                        os.remove(xmp_path)
                except OSError as e:
                    print(f"[red]Error deleting {xmp_path}: {e}[/red]")
                pbar.update(0) # Tqdm iterates automatically, no need manual update if iterating list

        # Remove the temporary directory
        if self._temp_xmp_dir and os.path.exists(self._temp_xmp_dir):
            try:
                shutil.rmtree(self._temp_xmp_dir)
                # print(f"[dim]Removed temporary directory: {self._temp_xmp_dir}[/dim]")
            except OSError as e:
                print(f"[red]Error removing temp dir {self._temp_xmp_dir}: {e}[/red]")
