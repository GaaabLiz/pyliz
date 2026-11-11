"""Snapshot models, validation rules, enum values and shared configuration.

Models remain mutable. Association construction does not scan the source tree;
captured sizes come from the copied-content manifest. Validation normalizes
original paths, and compatibility helpers delegate copy and example generation
to dedicated modules.
"""

import hashlib
import math
import platform
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import ClassVar, Optional

from pylizlib.core.os.snap.copy_strategy import CopyMetadataMode, DirectoryCopyStrategy, ExtendedMetadataCopyStrategy, SequentialFileCopyStrategy
from pylizlib.core.os.snap.integrity import IntegrityManifest, integrity_manifest_size_mb, validate_integrity_manifest
from pylizlib.core.os.snap.storage.archive_limits import DEFAULT_MAX_ARCHIVE_ENTRIES, DEFAULT_MAX_ARCHIVE_UNCOMPRESSED_BYTES
from pylizlib.core.os.snap.storage.original_paths import normalize_original_path


def validate_directory_component(value: str, field_name: str = "directory name", allow_empty: bool = False) -> str:
    """Validate a single portable path component used inside a snapshot."""
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string.")
    if allow_empty and value == "":
        return value
    if not value or value in {".", ".."} or "/" in value or "\\" in value or ":" in value or "\x00" in value or Path(value).is_absolute() or Path(value).name != value:
        raise ValueError(f"{field_name} must be a single relative path component: {value!r}.")
    return value


@dataclass
class SnapDirAssociation:
    """
    Represents the association between an original directory and its copy within a snapshot.

    Attributes:
        index: A sequential identifier for the directory within the snapshot.
        original_path: The original, absolute path of the directory on the system.
        folder_id: A unique random identifier for this specific directory association.
        mb_size: The size of the directory in megabytes.
    """

    index: int
    original_path: str
    folder_id: str
    mb_size: float | None = None
    integrity_manifest: IntegrityManifest | None = None
    _current_index: ClassVar[int] = 0

    def __post_init__(self):
        """Validate and normalize without scanning the possibly remote source tree."""
        self._storage_name = None
        self._storage_id = None
        self._path_initialized = False
        self.validate()

    def record_captured_content(self, manifest: IntegrityManifest) -> None:
        """Store the verified manifest and size of the content just captured."""
        validate_integrity_manifest(manifest)
        self.integrity_manifest = {path: dict(entry) for path, entry in manifest.items()}
        self.mb_size = integrity_manifest_size_mb(self.integrity_manifest)

    def validate(self) -> None:
        """Validate the fields that define this association's stored path."""
        if type(self.index) is not int:
            raise TypeError("Snapshot directory index must be an integer.")
        if self.index < 0:
            raise ValueError("Snapshot directory index cannot be negative.")
        if not isinstance(self.original_path, str):
            raise TypeError("Snapshot directory original_path must be a string.")
        if not self.original_path or "\x00" in self.original_path:
            raise ValueError("Snapshot directory original_path must be a non-empty path without NUL characters.")
        if not isinstance(self.folder_id, str) or not self.folder_id:
            raise TypeError("Snapshot directory folder_id must be a non-empty string.")
        self.original_path = normalize_original_path(
            self.original_path,
            allow_relative=not self._path_initialized,
        )
        self._path_initialized = True
        if self.mb_size is not None:
            if type(self.mb_size) not in (int, float):
                raise TypeError("Snapshot directory mb_size must be a non-negative number or None.")
            if self.mb_size < 0 or (type(self.mb_size) is float and not math.isfinite(self.mb_size)):
                raise ValueError("Snapshot directory mb_size must be finite and non-negative.")
        validate_integrity_manifest(self.integrity_manifest)
        if self.integrity_manifest is not None:
            # The captured tree is authoritative; a copied source-size estimate
            # from older metadata must not override the stored content size.
            self.mb_size = integrity_manifest_size_mb(self.integrity_manifest)

    @classmethod
    def next_index(cls):
        """
        Increments and returns the class-level index for new directory associations.

        Returns:
            The next integer index.
        """
        cls._current_index += 1
        return cls._current_index

    @property
    def directory_name(self) -> str:
        """Return the persistent physical name for this association's stored copy."""
        self.validate()
        stored_name = getattr(self, "_storage_name", None)
        stored_id = getattr(self, "_storage_id", None)
        if stored_name is not None and stored_id == self.folder_id:
            return validate_directory_component(stored_name, "snapshot association storage name")
        digest = hashlib.sha256(self.folder_id.encode("utf-8")).hexdigest()
        return f"assoc-{digest}"

    @property
    def _legacy_directory_name(self) -> str:
        """Return the index-and-basename name used by snapshots before storage IDs."""
        self.validate()
        basename = Path(self.original_path).name
        if not basename:
            raise ValueError("Snapshot directory original_path must have a final path component.")
        return validate_directory_component(f"{self.index}-{basename}")

    def _set_storage_name(self, storage_name: str) -> None:
        """Retain a physical name loaded from metadata or copied from a clone."""
        self._storage_name = validate_directory_component(storage_name, "snapshot association storage name")
        self._storage_id = self.folder_id

    @staticmethod
    def gen_random(
        source_folder_for_choices: Path,
        folder_id_length: int = 4,
    ) -> "SnapDirAssociation":
        """
        Generates a single, random SnapDirAssociation for testing purposes.

        Args:
            source_folder_for_choices: A directory from which a random subfolder will be chosen.
            folder_id_length: The length of the random `folder_id`.

        Returns:
            A new `SnapDirAssociation` instance with random data.
        """
        from pylizlib.core.os.snap.factories import gen_random_association

        return gen_random_association(source_folder_for_choices, folder_id_length)

    @staticmethod
    def gen_random_list(count: int, source_folder_for_choices: Path) -> list["SnapDirAssociation"]:
        """
        Generates a list of random SnapDirAssociation objects for testing.

        Args:
            count: The number of associations to generate.
            source_folder_for_choices: The directory from which random subfolders will be chosen.

        Returns:
            A list of new `SnapDirAssociation` instances.
        """
        from pylizlib.core.os.snap.factories import gen_random_association_list

        return gen_random_association_list(count, source_folder_for_choices)

    def copy_install_to(
        self,
        catalogue_target_path: Path,
        progress_callback=None,
        message_callback=None,
        *,
        copy_strategy: DirectoryCopyStrategy | None = None,
        manifest: IntegrityManifest | None = None,
        expected_manifest: IntegrityManifest | None = None,
    ):
        """Copy this association using the configured directory-copy strategy."""
        from pylizlib.core.os.snap.storage.association import copy_association

        return copy_association(self, catalogue_target_path, progress_callback, message_callback, copy_strategy=copy_strategy, manifest=manifest, expected_manifest=expected_manifest)


class SnapEditType(Enum):
    """Supported directory-association changes: add, remove or rename by identity."""

    ADD_DIR = "Add"
    REMOVE_DIR = "Remove"
    RENAME_DIR = "Rename"


class BackupType(Enum):
    """Select live associated directories or the complete stored snapshot tree."""

    ASSOCIATED_DIRECTORIES = 1
    SNAPSHOT_DIRECTORY = 2


@dataclass
class SnapshotBackupInfo:
    """Metadata read from a backup archive, with filename fallback for legacy ZIPs."""

    path: Path
    file_name: str
    snapshot_id: str | None
    backup_type: BackupType | None
    prefix: str
    created_at: datetime | None
    is_export: bool


class SnapshotSortKey(Enum):
    """Snapshot attribute names accepted by the stable sorting helper."""

    ID = "id"
    NAME = "name"
    DESCRIPTION = "desc"
    AUTHOR = "author"
    DATE_CREATED = "date_created"
    DATE_MODIFIED = "date_modified"
    DATE_LAST_USED = "date_last_used"
    DATE_LAST_MODIFIED = "date_last_modified"
    ASSOC_DIR_MB_SIZE = "get_assoc_dir_mb_size"


@dataclass
class SnapEditAction:
    """
    Represents a single atomic change (addition, removal or rename of a directory)
    to a snapshot's structure.

    Attributes:
        action_type: The type of edit (ADD_DIR, REMOVE_DIR or RENAME_DIR).
        timestamp: The time the action was created.
        new_path: The path of the directory being added (for ADD_DIR actions).
        folder_id_to_remove: The ID of the folder to remove (for REMOVE_DIR actions).
        directory_name_to_remove: The name of the directory to remove (for REMOVE_DIR actions).
        folder_id: The stable association ID, independent of directory names and indices.
    """

    action_type: SnapEditType
    timestamp: datetime = field(default_factory=datetime.now)
    new_path: str = ""
    folder_id_to_remove: str = ""
    directory_name_to_remove: str = ""
    old_directory_name: str = ""
    new_directory_name: str = ""
    folder_id: str = ""

    def __post_init__(self):
        """Validate a newly constructed edit before it can be used in a filesystem plan."""
        self._path_initialized = False
        self.validate()

    def validate(self) -> None:
        """Validate every action field before it can participate in a filesystem plan."""
        if not isinstance(self.action_type, SnapEditType):
            raise TypeError("Snapshot edit action_type must be a SnapEditType.")
        if not isinstance(self.timestamp, datetime):
            raise TypeError("Snapshot edit timestamp must be a datetime.")
        for name in ("new_path", "folder_id_to_remove", "folder_id"):
            value = getattr(self, name)
            if not isinstance(value, str):
                raise TypeError(f"Snapshot edit {name} must be a string.")
        if self.action_type == SnapEditType.ADD_DIR and self.new_path:
            self.new_path = normalize_original_path(
                self.new_path,
                allow_relative=not self._path_initialized,
            )
        self._path_initialized = True
        for name in ("directory_name_to_remove", "old_directory_name", "new_directory_name"):
            validate_directory_component(getattr(self, name), name, allow_empty=True)


@dataclass
class SnapshotSettings:
    """
    Holds configuration settings for snapshot management.

    Attributes:
        json_filename: The name of the snapshot metadata file.
        backup_path: The directory to store backups.
        backup_pre_install: Whether to create a backup before installing a snapshot.
        backup_pre_modify: Whether to create a backup before modifying a snapshot.
        backup_pre_delete: Whether to create a backup before deleting a snapshot.
        install_with_everyone_full_control: If on Windows, whether to grant 'Everyone'
                                            full control over installed directories (default False).
        snap_id_length: The character length for new snapshot IDs.
        folder_id_length: The character length for new folder association IDs.
        copy_strategy: Strategy object used to copy directory trees.
        copy_metadata_mode: Select the existing basic metadata behavior or the
                            stricter platform-supported extended metadata copier.
        allow_unverified_legacy_snapshots: Allow installation without a content manifest.
        archive_temp_directory: Filesystem location for temporary ZIP extraction.
        max_archive_uncompressed_bytes: Maximum total expanded size accepted on import/restore.
        max_archive_entries: Maximum number of ZIP members accepted on import/restore.
    """

    json_filename: str = "snapshot.json"
    backup_path: Path | None = None
    backup_pre_install: bool = False
    backup_pre_modify: bool = False
    backup_pre_delete: bool = False
    install_with_everyone_full_control: bool = False
    snap_id_length: int = 20
    folder_id_length: int = 6
    copy_strategy: DirectoryCopyStrategy = field(default_factory=SequentialFileCopyStrategy)
    allow_unverified_legacy_snapshots: bool = False
    copy_metadata_mode: CopyMetadataMode = CopyMetadataMode.BASIC
    archive_temp_directory: Path | None = None
    max_archive_uncompressed_bytes: int | None = DEFAULT_MAX_ARCHIVE_UNCOMPRESSED_BYTES
    max_archive_entries: int | None = DEFAULT_MAX_ARCHIVE_ENTRIES

    def __setattr__(self, name, value):
        """Keep the selected copier in sync when settings are changed at runtime."""
        if name == "copy_strategy":
            if not isinstance(value, DirectoryCopyStrategy):
                raise TypeError("copy_strategy must implement DirectoryCopyStrategy.")
            mode = self.__dict__.get("copy_metadata_mode", CopyMetadataMode.BASIC)
            if mode is CopyMetadataMode.EXTENDED and not isinstance(value, ExtendedMetadataCopyStrategy):
                value = ExtendedMetadataCopyStrategy(value)
        elif name == "copy_metadata_mode":
            if not isinstance(value, CopyMetadataMode):
                raise TypeError("copy_metadata_mode must be a CopyMetadataMode.")
            previous_mode = self.__dict__.get("copy_metadata_mode")
            strategy = self.__dict__.get("copy_strategy")
            if value is CopyMetadataMode.EXTENDED and isinstance(strategy, DirectoryCopyStrategy) and not isinstance(strategy, ExtendedMetadataCopyStrategy):
                object.__setattr__(self, "copy_strategy", ExtendedMetadataCopyStrategy(strategy))
            elif previous_mode is CopyMetadataMode.EXTENDED and value is CopyMetadataMode.BASIC and isinstance(strategy, ExtendedMetadataCopyStrategy):
                object.__setattr__(self, "copy_strategy", strategy.delegate)
        object.__setattr__(self, name, value)

    def __post_init__(self):
        """Validate copy configuration and the legacy-install flag."""
        if not isinstance(self.copy_strategy, DirectoryCopyStrategy):
            raise TypeError("copy_strategy must implement DirectoryCopyStrategy.")
        if type(self.allow_unverified_legacy_snapshots) is not bool:
            raise TypeError("allow_unverified_legacy_snapshots must be a boolean.")
        if not isinstance(self.copy_metadata_mode, CopyMetadataMode):
            raise TypeError("copy_metadata_mode must be a CopyMetadataMode.")
        if self.archive_temp_directory is not None and not isinstance(self.archive_temp_directory, Path):
            raise TypeError("archive_temp_directory must be a pathlib.Path or None.")
        for name in ("max_archive_uncompressed_bytes", "max_archive_entries"):
            limit = getattr(self, name)
            if limit is not None and type(limit) is not int:
                raise TypeError(f"{name} must be a non-negative integer or None.")
            if limit is not None and limit < 0:
                raise ValueError(f"{name} cannot be negative.")

    @property
    def bck_before_install_enabled(self) -> bool:
        """Checks if backup before installation is enabled and a path is set."""
        return self.backup_pre_install and self.backup_path is not None

    @property
    def bck_before_modify_enabled(self) -> bool:
        """Checks if backup before modification is enabled and a path is set."""
        return self.backup_pre_modify and self.backup_path is not None

    @property
    def bck_before_delete_enabled(self) -> bool:
        """Checks if backup before deletion is enabled and a path is set."""
        return self.backup_pre_delete and self.backup_path is not None


@dataclass
class Snapshot:
    """
    Represents a snapshot, which is a collection of directory associations
    and metadata at a specific point in time.

    Attributes:
        id: A unique identifier for the snapshot.
        name: A user-friendly name for the snapshot.
        desc: A description of the snapshot's purpose or contents.
        author: The user who created the snapshot.
        directories: A list of `SnapDirAssociation` objects linking to the original directories.
        tags: A list of strings for categorizing the snapshot.
        date_created: The timestamp when the snapshot was created.
        date_modified: The timestamp when the snapshot's metadata was last modified.
        date_last_used: The timestamp when the snapshot was last installed.
        date_last_modified: The timestamp when the snapshot's contents were last updated
                            from the source directories.
        data: A dictionary for storing custom, arbitrary key-value data.
        capture_started_at: The UTC start time of the last complete content acquisition.
        capture_completed_at: The UTC completion time of the last complete content acquisition.
    """

    id: str
    name: str
    desc: str
    author: str = field(default="UnknownUser")
    directories: list[SnapDirAssociation] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    date_created: datetime = field(default_factory=datetime.now)
    date_modified: datetime | None = None
    date_last_used: datetime | None = None
    date_last_modified: datetime | None = None
    os_created: str = field(default_factory=platform.system)
    data: dict[str, str] = field(default_factory=dict)
    capture_started_at: datetime | None = None
    capture_completed_at: datetime | None = None

    def __post_init__(self):
        """Validate a new mutable snapshot and every contained association."""
        self.validate()

    def validate(self) -> None:
        """Validate snapshot metadata, including every association used for paths."""
        for name in ("id", "name", "desc", "author", "os_created"):
            if not isinstance(getattr(self, name), str):
                raise TypeError(f"Snapshot {name} must be a string.")
        if not self.id:
            raise ValueError("Snapshot ID cannot be empty.")
        validate_directory_component(self.id, "Snapshot ID")
        if not isinstance(self.date_created, datetime):
            raise TypeError("Snapshot date_created must be a datetime.")
        for name in ("date_modified", "date_last_used", "date_last_modified"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, datetime):
                raise TypeError(f"Snapshot {name} must be a datetime or None.")
        for name in ("capture_started_at", "capture_completed_at"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, datetime):
                raise TypeError(f"Snapshot {name} must be a timezone-aware datetime or None.")
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError(f"Snapshot {name} must include an explicit timezone.")
        if self.capture_started_at is not None and self.capture_completed_at is not None:
            if self.capture_completed_at < self.capture_started_at:
                raise ValueError("Snapshot capture_completed_at cannot precede capture_started_at.")
        if not isinstance(self.directories, list) or any(not isinstance(item, SnapDirAssociation) for item in self.directories):
            raise TypeError("Snapshot directories must be a list of SnapDirAssociation objects.")
        for association in self.directories:
            association.validate()
        directory_names = [association.directory_name for association in self.directories]
        folder_ids = [association.folder_id for association in self.directories]
        if len(set(directory_names)) != len(directory_names):
            raise ValueError("Snapshot association directory names must be unique.")
        if len(set(folder_ids)) != len(folder_ids):
            raise ValueError("Snapshot association folder IDs must be unique.")
        if not isinstance(self.tags, list) or any(not isinstance(tag, str) for tag in self.tags):
            raise TypeError("Snapshot tags must be a list of strings.")
        if not isinstance(self.data, dict) or any(not isinstance(key, str) or not isinstance(value, str) for key, value in self.data.items()):
            raise TypeError("Snapshot data must be a dictionary of strings.")

    @property
    def tags_as_string(self) -> str:
        """Returns the list of tags as a single, comma-separated string."""
        return ", ".join(sorted(self.tags)) if self.tags else " "

    def get_for_table_array(self, key_list: list[str]) -> list[str]:
        """
        Generates a list of strings representing the snapshot's data for table display.

        Args:
            key_list: A list of keys to retrieve from the snapshot's data dictionary.

        Returns:
            A list of strings containing snapshot information in a specific order.
        """
        array = [self.name, self.desc]
        for key in key_list:
            value = self.data.get(key, "")
            array.append(value)
        array.append(self.date_created.strftime("%d/%m/%Y %H:%M:%S"))
        array.append(self.tags_as_string)
        return array

    @property
    def folder_name(self) -> str:
        """The name of the snapshot's folder in the catalogue, which is its ID."""
        return self.id

    @property
    def get_assoc_dir_mb_size(self) -> float:
        """
        Returns the sum of the mb_size of all associated directories.
        """
        return sum(d.mb_size for d in self.directories if d.mb_size is not None)

    def add_data_item(self, key: str, value: str) -> None:
        """
        Adds a key-value pair to the custom data dictionary.

        Args:
            key: The key for the data item.
            value: The value to store.
        """
        self.data[key] = value

    def remove_data_item(self, key: str) -> Optional[str]:
        """
        Removes an item from the data dictionary and returns its value.

        Args:
            key: The key of the item to remove.

        Returns:
            The value of the removed item, or None if the key was not found.
        """
        return self.data.pop(key, None)

    def has_data_item(self, key: str) -> bool:
        """
        Checks if a key exists in the data dictionary.

        Args:
            key: The key to check.

        Returns:
            True if the key exists, False otherwise.
        """
        return key in self.data

    def get_data_item(self, key: str, default: str = "") -> str:
        """
        Gets a value from the data dictionary, returning a default if the key is not found.

        Args:
            key: The key of the item to retrieve.
            default: The default value to return if the key is not found.

        Returns:
            The value associated with the key, or the default value.
        """
        return self.data.get(key, default)

    def clear_all_data(self) -> None:
        """Clears all items from the data dictionary."""
        self.data.clear()

    def edit_data_item(self, key: str, new_value: str) -> None:
        """
        Edits the value of an existing item in the data dictionary.

        Args:
            key: The key of the item to edit.
            new_value: The new value to set.

        Raises:
            KeyError: If the key does not exist in the data dictionary.
        """
        if key in self.data:
            self.data[key] = new_value
        else:
            raise KeyError(f"Key '{key}' not found in data.")

    def clone(self) -> "Snapshot":
        """
        Creates a deep, independent copy of the Snapshot instance.

        Returns:
            A new `Snapshot` object with the same data as the original.
        """
        return Snapshot(
            id=self.id,
            name=self.name,
            desc=self.desc,
            author=self.author,
            directories=[
                self._clone_association(dir_assoc)
                for dir_assoc in self.directories
            ],
            tags=list(self.tags),
            date_created=self.date_created,
            date_modified=self.date_modified,
            date_last_used=self.date_last_used,
            date_last_modified=self.date_last_modified,
            os_created=self.os_created,
            data=dict(self.data),
            capture_started_at=self.capture_started_at,
            capture_completed_at=self.capture_completed_at,
        )

    @staticmethod
    def _clone_association(dir_assoc: SnapDirAssociation) -> SnapDirAssociation:
        """Clone all association metadata while retaining its stable storage path."""
        clone = SnapDirAssociation(
            index=dir_assoc.index,
            original_path=dir_assoc.original_path,
            folder_id=dir_assoc.folder_id,
            mb_size=dir_assoc.mb_size,
            integrity_manifest=(
                {path: dict(entry) for path, entry in dir_assoc.integrity_manifest.items()}
                if dir_assoc.integrity_manifest is not None
                else None
            ),
        )
        clone._set_storage_name(dir_assoc.directory_name)
        return clone
