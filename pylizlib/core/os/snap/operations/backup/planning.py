"""Resolve association restore policy and produce explicit source/staging plans."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from pylizlib.core.data.gen import gen_random_string
from pylizlib.core.os.snap.domain import SnapshotSettings
from pylizlib.core.os.snap.operations.archives import SnapshotIncompleteError, SnapshotLookup, _ArchiveMetadata
from pylizlib.core.os.snap.operations.backup_manifest import ArchivedAssociation
from pylizlib.core.os.snap.operations.destinations import validate_destructive_destinations
from pylizlib.core.os.snap.storage.context import SnapshotStorage
from pylizlib.core.os.snap.storage.paths import get_snapshot_json_path, get_snapshot_path
from pylizlib.core.os.snap.storage.transactions import recover_storage_transactions


@dataclass(frozen=True)
class AssociationRestoreTask:
    """Keep extracted input, prepared staging and target distinct throughout restore.

    Attributes:
        folder_id (str): Stable association identity recorded in the manifest.
        extracted_dir (Path): Input directory owned by the extraction context.
        staged_dir (Path): Generated sibling receiving the copy before publication.
        destination (Path): Validated live directory to replace.
        backup_dest (Path): Generated sibling retaining the previous target.
        had_original (bool): Whether a target entry existed when planning began.
    """

    folder_id: str
    extracted_dir: Path
    staged_dir: Path
    destination: Path
    backup_dest: Path
    had_original: bool


class RestorePlanner:
    """Validate archive completeness and destination policy before opening a journal."""

    def __init__(self, path_catalogue: Path, settings: SnapshotSettings, lookup: SnapshotLookup):
        """Bind catalogue policy and optional legacy metadata lookup."""
        self.path_catalogue = path_catalogue
        self.settings = settings
        self.lookup = lookup

    def associations_from(self, metadata: _ArchiveMetadata) -> tuple[list[ArchivedAssociation], str | None]:
        """Resolve the associations and OS that govern an associated-directory restore."""
        info = metadata.info
        if not info.snapshot_id:
            raise ValueError("Could not determine snapshot ID from associated-directories archive metadata.")

        if metadata.associations is not None:
            origin_os = metadata.os_created
            associations = list(metadata.associations)
            if origin_os is None:
                snapshot = self.lookup.get_by_id(info.snapshot_id)
                if not snapshot:
                    raise ValueError("The archive does not record its originating OS and the snapshot metadata is unavailable.")
                origin_os = snapshot.os_created
        else:
            snapshot = self.lookup.get_by_id(info.snapshot_id)
            if not snapshot:
                raise ValueError(f"Snapshot with ID '{info.snapshot_id}' not found. Legacy associated-directories archives require an existing snapshot metadata entry.")
            snapshot_root = get_snapshot_path(snapshot.folder_name, self.path_catalogue)
            storage = SnapshotStorage(
                snapshot,
                self.settings,
                self.path_catalogue,
                snapshot_root,
                get_snapshot_json_path(snapshot.folder_name, self.path_catalogue, self.settings.json_filename),
            )
            recover_storage_transactions(storage)
            origin_os = snapshot.os_created
            associations = [ArchivedAssociation(association.folder_id, association.index, association.directory_name, association.original_path) for association in snapshot.directories]

        return associations, origin_os

    def resolve_destinations(
        self,
        associations: list[ArchivedAssociation],
        destination_mapping: Mapping[str, str | Path] | None,
        origin_os: str | None,
    ) -> list[Path]:
        """Validate association mapping and all paths before extraction or replacement."""
        mapping = destination_mapping or {}
        if any(not isinstance(folder_id, str) or not folder_id for folder_id in mapping):
            raise TypeError("Destination mapping keys must be non-empty association IDs.")
        unknown_ids = set(mapping) - {association.folder_id for association in associations}
        if unknown_ids:
            raise ValueError(f"Destination mapping contains unknown association IDs: {', '.join(sorted(unknown_ids))}.")

        destination_inputs = []
        for association in associations:
            raw_destination = mapping.get(association.folder_id, association.original_path)
            if not isinstance(raw_destination, (str, os.PathLike)):
                raise TypeError(f"Restore destination for association '{association.folder_id}' must be a path.")
            destination_value = os.fspath(raw_destination)
            if not isinstance(destination_value, str):
                raise TypeError(f"Restore destination for association '{association.folder_id}' must be a string path.")
            if not destination_value or "\x00" in destination_value:
                raise ValueError(f"Restore destination for association '{association.folder_id}' must be non-empty and contain no NUL characters.")
            if association.folder_id not in mapping and not Path(destination_value).is_absolute():
                if PureWindowsPath(destination_value).is_absolute():
                    raise ValueError(f"Restore destination for association '{association.folder_id}' must be mapped for this platform.")
            destination_inputs.append((association.folder_id, destination_value))

        return validate_destructive_destinations(
            destination_inputs,
            catalogue_path=self.path_catalogue,
            origin_os=origin_os,
            operation="restore associated directories",
        )

    def build(
        self, temp_dir_path: Path, associations: list[ArchivedAssociation], destination_mapping: Mapping[str, str | Path] | None, manifest_name: str | None, origin_os: str | None
    ) -> list[AssociationRestoreTask]:
        """Validate every extracted association before planning sibling staging paths."""
        extracted_by_name = self._validate_extracted_associations(temp_dir_path, associations, manifest_name)

        destinations = self.resolve_destinations(associations, destination_mapping, origin_os)

        tasks = []
        for association, destination in zip(associations, destinations, strict=True):
            extracted_dir = extracted_by_name[association.directory_name]
            if not destination.parent.is_dir():
                raise FileNotFoundError(f"Parent directory for restore destination '{destination}' does not exist.")
            backup_dest = destination.with_name(f"{destination.name}_bck_{gen_random_string(6)}")
            try:
                destination.lstat()
                had_original = True
            except FileNotFoundError:
                had_original = False
            tasks.append((association.folder_id, extracted_dir, destination, backup_dest, had_original))

        planned = []
        for folder_id, extracted_dir, destination, initial_backup, had_original in tasks:
            staged_dir = destination.with_name(f"{destination.name}_staging_{gen_random_string(6)}")
            while staged_dir.exists() or staged_dir.is_symlink():
                staged_dir = destination.with_name(f"{destination.name}_staging_{gen_random_string(6)}")
            backup_dest = initial_backup
            while backup_dest.exists() or backup_dest.is_symlink():
                backup_dest = destination.with_name(f"{destination.name}_bck_{gen_random_string(6)}")
            planned.append(AssociationRestoreTask(folder_id, extracted_dir, staged_dir, destination, backup_dest, had_original))
        return planned

    @staticmethod
    def _validate_extracted_associations(temp_dir_path: Path, associations: list[ArchivedAssociation], manifest_name: str | None) -> dict[str, Path]:
        """Require exactly the expected directories, retaining empty associations.

        Args:
            temp_dir_path (Path): Extraction root owned by the caller.
            associations (list[ArchivedAssociation]): Complete expected association set.
            manifest_name (str | None): Manifest member to exclude from content checks.

        Returns:
            dict[str, Path]: Extracted entries by storage name, after complete validation.

        Raises:
            ValueError: If an empty archive restores no associations.
            SnapshotIncompleteError: If expected directories are missing or unexpected
                entries/non-directory roots are present.
            OSError: If enumeration or entry inspection fails.
        """
        dir_name_to_assoc = {association.directory_name: association for association in associations}
        extracted_entries = sorted(
            (entry for entry in temp_dir_path.iterdir() if entry.name != manifest_name),
            key=lambda entry: entry.name,
        )
        extracted_by_name = {entry.name: entry for entry in extracted_entries}
        missing_folders = [
            association.original_path for association in associations if association.directory_name not in extracted_by_name or not extracted_by_name[association.directory_name].is_dir()
        ]
        unexpected_entries = [entry.name for entry in extracted_entries if entry.name not in dir_name_to_assoc or not entry.is_dir()]
        if not associations and not extracted_entries:
            raise ValueError("No associated directories were restored from the backup archive.")
        if missing_folders or unexpected_entries:
            raise SnapshotIncompleteError("Associated-directories restore", missing_folders, unexpected_entries)

        return extracted_by_name
