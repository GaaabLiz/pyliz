"""Catalogue ZIP import/export independent of the public catalogue implementation."""

import json
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Protocol

from pylizlib.core.log.pylizLogger import logger
from pylizlib.core.os.snap.domain import BackupType, Snapshot, SnapshotSettings
from pylizlib.core.os.snap.operations.backup.associations import association_identities
from pylizlib.core.os.snap.operations.backup_manifest import BACKUP_MANIFEST_NAME, parse_backup_manifest
from pylizlib.core.os.snap.serializer import SnapshotSerializer
from pylizlib.core.os.snap.storage.archives import extract_zip, write_verified_zip
from pylizlib.core.os.snap.storage.coordination import coordinated
from pylizlib.core.os.snap.storage.paths import assert_no_operational_storage, get_snapshot_path
from pylizlib.core.os.snap.storage.publication import publish_snapshot_tree, validate_staged_snapshot_tree
from pylizlib.core.os.snap.storage.tree import iter_tree_entries_strict


class CatalogueQuery(Protocol):
    """Catalogue query capabilities used by import/export; implementations may recover pending work."""

    def get_all(self, *, strict: bool = False) -> list[Snapshot]:
        """List entries with the catalogue's existing strict error policy.

        Args:
            strict (bool): Propagate filesystem errors when True; malformed/domain-invalid catalogue entries remain
                logged and skipped.

        Returns:
            list[Snapshot]: List entries with the catalogue's existing strict error policy.

        Notes:
            The catalogue may recover pending work before scanning. strict controls filesystem errors, not whether
            invalid metadata is included.
        """
        ...

    def exists(self, snap_id: str) -> bool:
        """Use metadata-based catalogue lookup to identify existing IDs.

        Args:
            snap_id (str): Snapshot ID identifying the catalogue entry, rather than its display name.

        Returns:
            bool: Use metadata-based catalogue lookup to identify existing IDs.

        Notes:
            The catalogue may recover pending work and then validate metadata; this capability is not equivalent to
            Path.exists().
        """
        ...


class CatalogueTransferService:
    """Import or export snapshot trees while retaining conflict/error policies.

    Attributes:
        path_catalogue (Path): Catalogue root retained by this collaborator.
        settings (SnapshotSettings): Mutable snapshot settings retained by reference; no defensive copy is made.
        query (CatalogueQuery): Query text or regex source; regex syntax is compiled at search time.
    """

    def __init__(self, path_catalogue: Path, settings: SnapshotSettings, query: CatalogueQuery):
        """Capture current paths/settings and the narrow catalogue query capabilities.

        Args:
            path_catalogue (Path): Catalogue root retained by this collaborator.
            settings (SnapshotSettings): Mutable snapshot settings retained by reference; no defensive copy is made.
            query (CatalogueQuery): Narrow catalogue query collaborator; its lookups retain existing recovery side
                effects.

        Returns:
            None: No return value.
        """
        self.path_catalogue = path_catalogue
        self.settings = settings
        self.query = query

    @contextmanager
    def _extract_archive(self, zip_path: Path) -> Iterator[Path]:
        """Validate a transfer archive and expose its bounded temporary extraction tree.

        Args:
            zip_path (Path): Existing .zip archive to extract.

        Yields:
            Path: Temporary extraction root, removed when the import finishes.

        Raises:
            ValueError: The path is not an existing .zip file.
            OSError: Staging or extraction fails.
        """
        if not zip_path.is_file() or zip_path.suffix != ".zip":
            raise ValueError(f"Provided path '{zip_path}' is not a valid .zip file.")

        temp_parent = self.settings.archive_temp_directory or self.path_catalogue
        temp_parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".archive_staging_", dir=temp_parent) as temp_dir:
            temp_dir_path = Path(temp_dir)
            extract_zip(
                zip_path,
                temp_dir_path,
                max_entries=self.settings.max_archive_entries,
                max_uncompressed_bytes=self.settings.max_archive_uncompressed_bytes,
                additional_space_paths=[self.path_catalogue],
            )
            yield temp_dir_path

    @coordinated("path_catalogue")
    def export_catalogue(self, destination_path: Path, file_name: str = "catalogue_export.zip"):
        """Exports the entire catalogue to a single zip file.

        Args:
            destination_path (Path): The folder where the exported zip file will be saved.
            file_name (str): The name for the output zip file.

        Returns:
            Path | None: Published ZIP path, or None when the catalogue has no snapshots.

        Raises:
            SnapshotBusyError: Another operation owns the catalogue, or an observer attempts a modifying call.
        """
        destination_path.mkdir(parents=True, exist_ok=True)
        zip_path = destination_path.joinpath(file_name)

        snapshots = self.query.get_all(strict=True)
        if not snapshots:
            logger.warning("Catalogue is empty. Nothing to export.")
            return

        def files_to_archive():
            """Yield catalogue-relative tree entries after strict metadata enumeration.

            Yields:
                tuple[Path, Path]: Source entry and relative archive name, including empty directories.
            """
            for snap in snapshots:
                snap_dir = get_snapshot_path(snap.id, self.path_catalogue)
                for tree_entry in iter_tree_entries_strict(snap_dir):
                    yield tree_entry, tree_entry.relative_to(self.path_catalogue)

        return write_verified_zip(zip_path, files_to_archive())

    @coordinated("path_catalogue")
    def import_catalogue(self, zip_path: Path):
        """Imports all snapshots from a catalogue zip file, skipping existing ones.

        Args:
            zip_path (Path): The path to the catalogue .zip file.

        Returns:
            None: No return value.

        Raises:
            SnapshotBusyError: Another operation owns the catalogue, or an observer attempts a modifying call.
            ValueError: If the provided path is not a valid .zip file or contains operational transaction storage.
            IOError: If the zip file fails to extract.
        """
        with self._extract_archive(zip_path) as temp_dir_path:
            # Reject imported recovery instructions before publishing any catalogue entry.
            assert_no_operational_storage(temp_dir_path)
            for entry in temp_dir_path.iterdir():
                if entry.is_dir():
                    assert_no_operational_storage(entry)

            # Iterate through extracted folders and import them
            for potential_snap_dir in temp_dir_path.iterdir():
                self._import_entry(potential_snap_dir)

    @coordinated("path_catalogue")
    def import_snapshot(self, zip_path: Path):
        """Imports a snapshot from a zip file into the catalogue.

        Args:
            zip_path (Path): The path to the .zip file to import.

        Returns:
            None: No return value.

        Raises:
            SnapshotBusyError: Another operation owns the catalogue, or an observer attempts a modifying call.
            ValueError: If the path is not a valid zip file, if the zip is corrupted, if the snapshot.json is missing,
                contains operational transaction storage, or if a snapshot with the same ID already exists.
            IOError: If the zip file fails to extract.
        """
        with self._extract_archive(zip_path) as temp_dir_path:
            # Validate the content and get snapshot
            snapshot_to_import = self._read_imported_snapshot(temp_dir_path)

            # Check for ID conflict
            if self.query.exists(snapshot_to_import.id):
                raise ValueError(f"A snapshot with the ID '{snapshot_to_import.id}' already exists in the catalogue.")

            def validate_import(staged_path: Path) -> None:
                """Check copied metadata and association directories before publication.

                Args:
                    staged_path (Path): Completed private snapshot tree to inspect before publication.

                Returns:
                    None: No return value.
                """
                validate_staged_snapshot_tree(staged_path, snapshot_to_import.id, self.settings.json_filename)

            # Copy the extracted folder to the catalogue
            publish_snapshot_tree(
                temp_dir_path,
                snapshot_to_import.id,
                self.path_catalogue,
                prepare_staging=validate_import,
                copy_strategy=self.settings.copy_strategy,
                operation="Snapshot import",
            )
        logger.info("Imported snapshot id=%s", snapshot_to_import.id)

    def _import_entry(self, potential_snap_dir: Path) -> None:
        """Import one extracted entry; log and skip per-entry failures as before.

        Only its raw ID is inspected here. Full domain validation belongs to
        single-snapshot import and must not be added to this legacy batch flow.

        Args:
            potential_snap_dir (Path): One extracted batch-import entry; non-directories and invalid entries are
                skipped under legacy policy.

        Returns:
            None: No return value.
        """
        if not potential_snap_dir.is_dir():
            return

        json_path = potential_snap_dir / self.settings.json_filename
        if not json_path.is_file():
            logger.warning(f"Skipping directory '{potential_snap_dir.name}' as it does not contain a snapshot json file.")
            return

        # Read just the ID to avoid loading the whole object unnecessarily
        try:
            data = json.loads(SnapshotSerializer.read_text(json_path))
            snap_id = data.get("id")
            if not snap_id:
                logger.warning(f"Skipping directory '{potential_snap_dir.name}' as snapshot ID is missing from json.")
                return

            # Check for ID conflict
            if self.query.exists(snap_id):
                logger.info(f"Snapshot with ID '{snap_id}' already exists. Skipping import.")
                return

            # Copy the extracted folder to the catalogue
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

    def _read_imported_snapshot(self, temp_dir_path: Path) -> Snapshot:
        """Read extracted metadata and validate its optional SD export manifest.

        Args:
            temp_dir_path (Path): Extraction root owned by import_snapshot.

        Returns:
            Snapshot: Parsed domain model after identity/association checks. A valid export manifest is removed so it
                does not enter stored snapshot content.

        Raises:
            ValueError: If operational transaction storage is present, JSON is missing/invalid or the optional export
                manifest disagrees with its type, ID or association set.
            OSError: If reading or removing a manifest fails outside the mapped errors.
        """
        assert_no_operational_storage(temp_dir_path)
        json_path = temp_dir_path / self.settings.json_filename
        if not json_path.is_file():
            raise ValueError(f"The zip file does not contain a snapshot json file ('{self.settings.json_filename}').")

        try:
            snapshot_to_import = SnapshotSerializer.from_json(json_path)
        except Exception as e:
            raise ValueError(f"Failed to read snapshot data from json: {e}")

        backup_manifest_path = temp_dir_path / BACKUP_MANIFEST_NAME
        if backup_manifest_path.is_file():
            try:
                backup_manifest = parse_backup_manifest(json.loads(backup_manifest_path.read_text(encoding="utf-8")))
            except Exception as error:
                raise ValueError(f"Snapshot export contains an invalid backup manifest: {error}") from error
            if backup_manifest.backup_type != BackupType.SNAPSHOT_DIRECTORY or backup_manifest.snapshot_id != snapshot_to_import.id:
                raise ValueError("Snapshot export manifest does not match its snapshot JSON.")
            manifest_associations = association_identities(backup_manifest.associations)
            snapshot_associations = association_identities(snapshot_to_import.directories)
            if manifest_associations != snapshot_associations:
                raise ValueError("Snapshot export associations do not match its snapshot JSON.")
            backup_manifest_path.unlink()
        return snapshot_to_import
