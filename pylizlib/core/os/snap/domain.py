"""
Core domain models for the snapshot system.

Defines all data structures (dataclasses, enums) that represent the snapshot
domain.  This module has no business logic and no I/O — it only holds state
and lightweight helpers that compute properties from that state.

Classes:
    SnapDirAssociation  – Links an original directory to its in-snapshot copy.
    SnapEditType        – Enum: ADD_DIR | REMOVE_DIR.
    BackupType          – Enum: ASSOCIATED_DIRECTORIES | SNAPSHOT_DIRECTORY.
    SnapshotBackupInfo  – Parsed metadata from a backup archive filename.
    SnapshotSortKey     – Enum of sortable Snapshot attributes.
    SnapEditAction      – A single atomic change to a snapshot's structure.
    SnapshotSettings    – Configuration for snapshot management.
    Snapshot            – A named collection of directory associations.
"""

import shutil
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import ClassVar, Optional

from pylizlib.core.data.gen import gen_random_string
from pylizlib.core.log.pylizLogger import logger
from pylizlib.core.os.path import random_subfolder
from pylizlib.core.os.utils import get_folder_size_mb


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
    _current_index: ClassVar[int] = 0

    def __post_init__(self):
        self.original_path = Path(self.original_path).as_posix()
        if self.mb_size is None:
            try:
                self.mb_size = get_folder_size_mb(Path(self.original_path))
            except FileNotFoundError:
                self.mb_size = 0.0  # Handle missing directory
            except Exception as e:  # Catch other potential errors from os.walk/getsize
                logger.error(f"Error calculating size for {self.original_path}: {e}")
                self.mb_size = 0.0

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
        """The name of the directory when copied into the snapshot folder."""
        return self.index.__str__() + "-" + Path(self.original_path).name

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
        return SnapDirAssociation(
            index=SnapDirAssociation.next_index(),
            original_path=random_subfolder(source_folder_for_choices).__str__(),
            folder_id=gen_random_string(folder_id_length),
        )

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
        return [SnapDirAssociation.gen_random(source_folder_for_choices) for _ in range(count)]

    def copy_install_to(self, catalogue_target_path: Path):
        """
        Copies the entire content of the directory specified by `original_path`
        into a subdirectory within the given `catalogue_target_path`.

        The new subdirectory will be named using the `directory_name` property.

        Args:
            catalogue_target_path: The base path in the catalogue where the directory
                                   content will be copied.
        """
        source = Path(self.original_path)
        destination = catalogue_target_path.joinpath(self.directory_name)
        destination.mkdir(parents=True, exist_ok=True)

        for src_path in source.iterdir():
            dst_path = destination / src_path.name
            if src_path.is_dir():
                shutil.copytree(src_path, dst_path)
            else:
                shutil.copy2(src_path, dst_path)


class SnapEditType(Enum):
    ADD_DIR = "Add"
    REMOVE_DIR = "Remove"


class BackupType(Enum):
    ASSOCIATED_DIRECTORIES = 1
    SNAPSHOT_DIRECTORY = 2


@dataclass
class SnapshotBackupInfo:
    """Metadata parsed from a backup archive filename."""

    path: Path
    file_name: str
    snapshot_id: str | None
    backup_type: BackupType | None
    prefix: str
    created_at: datetime | None
    is_export: bool


class SnapshotSortKey(Enum):
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
    Represents a single atomic change (an addition or removal of a directory)
    to a snapshot's structure.

    Attributes:
        action_type: The type of edit (ADD_DIR or REMOVE_DIR).
        timestamp: The time the action was created.
        new_path: The path of the directory being added (for ADD_DIR actions).
        folder_id_to_remove: The ID of the folder to remove (for REMOVE_DIR actions).
        directory_name_to_remove: The name of the directory to remove (for REMOVE_DIR actions).
    """

    action_type: SnapEditType
    timestamp: datetime = field(default_factory=datetime.now)
    new_path: str = ""
    folder_id_to_remove: str = ""
    directory_name_to_remove: str = ""


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
                                            full control over installed directories.
        snap_id_length: The character length for new snapshot IDs.
        folder_id_length: The character length for new folder association IDs.
    """

    json_filename: str = "snapshot.json"
    backup_path: Path | None = None
    backup_pre_install: bool = False
    backup_pre_modify: bool = False
    backup_pre_delete: bool = False
    install_with_everyone_full_control: bool = True
    snap_id_length: int = 20
    folder_id_length: int = 6

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
    data: dict[str, str] = field(default_factory=dict)

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
                SnapDirAssociation(
                    index=dir_assoc.index,
                    original_path=dir_assoc.original_path,
                    folder_id=dir_assoc.folder_id,
                    mb_size=dir_assoc.mb_size,
                )
                for dir_assoc in self.directories
            ],
            tags=list(self.tags),
            date_created=self.date_created,
            date_modified=self.date_modified,
            date_last_used=self.date_last_used,
            date_last_modified=self.date_last_modified,
            data=dict(self.data),
        )
