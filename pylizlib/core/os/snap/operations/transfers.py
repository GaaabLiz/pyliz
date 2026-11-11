"""Catalogue ZIP import/export independent of the public catalogue implementation."""

import json
import tempfile
from pathlib import Path
from typing import Protocol

from pylizlib.core.log.pylizLogger import logger
from pylizlib.core.os.snap.domain import Snapshot, SnapshotSettings
from pylizlib.core.os.snap.serializer import SnapshotSerializer
from pylizlib.core.os.snap.storage.archives import extract_zip, write_verified_zip
from pylizlib.core.os.snap.storage.paths import get_snapshot_path
from pylizlib.core.os.snap.storage.publication import publish_snapshot_tree
from pylizlib.core.os.snap.storage.tree import iter_files_strict


class CatalogueQuery(Protocol):
    """Read operations required by catalogue import and export."""

    def get_all(self, *, strict: bool = False) -> list[Snapshot]:
        """List entries with the catalogue's existing strict error policy."""
        ...

    def exists(self, snap_id: str) -> bool:
        """Use metadata-based catalogue lookup to identify existing IDs."""
        ...


class CatalogueTransferService:
    """Import or export snapshot trees while retaining conflict/error policies."""

    def __init__(self, path_catalogue: Path, settings: SnapshotSettings, query: CatalogueQuery):
        """Capture current paths/settings and a narrow read-only catalogue view."""
        self.path_catalogue = path_catalogue
        self.settings = settings
        self.query = query

    def export_catalogue(self, destination_path: Path, file_name: str = "catalogue_export.zip"):
        """
        Exports the entire catalogue to a single zip file.

        Args:
            destination_path: The folder where the exported zip file will be saved.
            file_name: The name for the output zip file.
        """
        destination_path.mkdir(parents=True, exist_ok=True)
        zip_path = destination_path.joinpath(file_name)

        snapshots = self.query.get_all(strict=True)
        if not snapshots:
            logger.warning("Catalogue is empty. Nothing to export.")
            return

        def files_to_archive():
            for snap in snapshots:
                snap_dir = get_snapshot_path(snap.id, self.path_catalogue)
                for file_path in iter_files_strict(snap_dir):
                    yield file_path, file_path.relative_to(self.path_catalogue)

        return write_verified_zip(zip_path, files_to_archive())

    def import_catalogue(self, zip_path: Path):
        """
        Imports all snapshots from a catalogue zip file, skipping existing ones.

        Args:
            zip_path: The path to the catalogue .zip file.

        Raises:
            ValueError: If the provided path is not a valid .zip file.
            IOError: If the zip file fails to extract.
        """
        if not zip_path.is_file() or zip_path.suffix != ".zip":
            raise ValueError(f"Provided path '{zip_path}' is not a valid .zip file.")

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)

            # 1. Extract the zip to a temporary directory
            extract_zip(zip_path, temp_dir_path)

            # 2. Iterate through extracted folders and import them
            for potential_snap_dir in temp_dir_path.iterdir():
                self._import_entry(potential_snap_dir)

    def import_snapshot(self, zip_path: Path):
        """
        Imports a snapshot from a zip file into the catalogue.

        Args:
            zip_path: The path to the .zip file to import.

        Raises:
            ValueError: If the path is not a valid zip file, if the zip is corrupted,
                        if the snapshot.json is missing, or if a snapshot with the same ID
                        already exists.
            IOError: If the zip file fails to extract.
        """
        if not zip_path.is_file() or zip_path.suffix != ".zip":
            raise ValueError(f"Provided path '{zip_path}' is not a valid .zip file.")

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)

            # 1. Extract the zip to a temporary directory
            extract_zip(zip_path, temp_dir_path)

            # 2. Validate the content and get snapshot
            json_path = temp_dir_path / self.settings.json_filename
            if not json_path.is_file():
                raise ValueError(f"The zip file does not contain a snapshot json file ('{self.settings.json_filename}').")

            try:
                snapshot_to_import = SnapshotSerializer.from_json(json_path)
            except Exception as e:
                raise ValueError(f"Failed to read snapshot data from json: {e}")

            # 3. Check for ID conflict
            if self.query.exists(snapshot_to_import.id):
                raise ValueError(f"A snapshot with the ID '{snapshot_to_import.id}' already exists in the catalogue.")

            # 4. Copy the extracted folder to the catalogue
            publish_snapshot_tree(
                temp_dir_path,
                snapshot_to_import.id,
                self.path_catalogue,
                copy_strategy=self.settings.copy_strategy,
                operation="Snapshot import",
            )

    def _import_entry(self, potential_snap_dir: Path) -> None:
        """Import one extracted entry; log and skip per-entry failures as before.

        Only its raw ID is inspected here. Full domain validation belongs to
        single-snapshot import and must not be added to this legacy batch flow.
        """
        if not potential_snap_dir.is_dir():
            return

        json_path = potential_snap_dir / self.settings.json_filename
        if not json_path.is_file():
            logger.warning(f"Skipping directory '{potential_snap_dir.name}' as it does not contain a snapshot json file.")
            return

        try:
            # Read just the ID to avoid loading the whole object unnecessarily
            data = json.loads(SnapshotSerializer.read_text(json_path))
            snap_id = data.get("id")
            if not snap_id:
                logger.warning(f"Skipping directory '{potential_snap_dir.name}' as snapshot ID is missing from json.")
                return

            # 3. Check for ID conflict
            if self.query.exists(snap_id):
                logger.info(f"Snapshot with ID '{snap_id}' already exists. Skipping import.")
                return

            # 4. Copy the extracted folder to the catalogue
            publish_snapshot_tree(
                potential_snap_dir,
                snap_id,
                self.path_catalogue,
                copy_strategy=self.settings.copy_strategy,
                operation="Catalogue import",
            )
            logger.info(f"Successfully imported snapshot with ID '{snap_id}'.")

        except Exception as e:
            logger.error(f"Failed to import snapshot from directory '{potential_snap_dir.name}': {e}")
