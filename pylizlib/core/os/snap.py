import json
import os
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import ClassVar, Optional, Callable

from pylizlib.core.data.gen import gen_random_string
from pylizlib.core.log.pylizLogger import logger
from pylizlib.core.os.path import random_subfolder, clear_folder_contents, clear_or_move_to_temp, duplicate_directory
from pylizlib.core.os.utils import get_folder_size_mb # New import


SnapshotProgressCallback = Callable[[str, int, int], None]


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
                self.mb_size = 0.0 # Handle missing directory
            except Exception as e: # Catch other potential errors from os.walk/getsize
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
    def gen_random(source_folder_for_choices: Path, folder_id_length: int = 4) -> 'SnapDirAssociation':
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
            folder_id=gen_random_string(folder_id_length)
        )

    @staticmethod
    def gen_random_list(count: int, source_folder_for_choices: Path) -> list['SnapDirAssociation']:
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
    timestamp: datetime = datetime.now()
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
    date_created: datetime = datetime.now()
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


    def clone(self) -> 'Snapshot':
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
            directories=[SnapDirAssociation(
                index=dir_assoc.index,
                original_path=dir_assoc.original_path,
                folder_id=dir_assoc.folder_id,
                mb_size=dir_assoc.mb_size
            ) for dir_assoc in self.directories],
            tags=list(self.tags),
            date_created=self.date_created,
            date_modified=self.date_modified,
            date_last_used=self.date_last_used,
            date_last_modified=self.date_last_modified,
            data=dict(self.data)
        )












class SnapshotUtils:

    @staticmethod
    def gen_random_snap(source_folder_for_choices: Path, id_length: int = 10, ) -> Snapshot:
        """
        Generates a random Snapshot instance for testing or demonstration purposes.

        Args:
            source_folder_for_choices: The path to a directory from which to pick random subdirectories.
            id_length: The length of the random string to be used for the snapshot's ID and name.

        Returns:
            A new Snapshot object with randomly generated data.
        """
        dirs = SnapDirAssociation.gen_random_list(3, source_folder_for_choices)
        return Snapshot(
            id=gen_random_string(id_length),
            name="Snapshot " + gen_random_string(id_length),
            desc="Randomly generated snapshot",
            author="User",
            directories=dirs,
            tags=["example", "test"],
        )


    @staticmethod
    def get_snapshot_from_path(path_snapshot: Path, json_filename: str) -> Snapshot | None:
        """
        Loads a Snapshot object from a directory containing a snapshot JSON file.

        Args:
            path_snapshot: The path to the snapshot's directory.
            json_filename: The name of the JSON file that contains the snapshot's data.

        Returns:
            A Snapshot object if the file is found and parsed correctly, otherwise None.
        
        Raises:
            ValueError: If the provided path is a file, not a directory.
            FileNotFoundError: If the path or the JSON file does not exist.
        """
        if path_snapshot.is_file():
            raise ValueError(f"The provided path {path_snapshot} is not a directory.")
        if not path_snapshot.exists():
            raise FileNotFoundError(f"The provided path {path_snapshot} does not exist.")
        path_snapshot_json = path_snapshot.joinpath(json_filename)
        if not path_snapshot_json.is_file():
            raise FileNotFoundError(f"No snapshot.json file found in {path_snapshot}.")
        return SnapshotSerializer.from_json(path_snapshot_json)

    @staticmethod
    def get_snapshot_path(folder_name: str, catalogue_path: Path) -> Path:
        """
        Constructs the full path to a snapshot's directory within the catalogue.

        Args:
            folder_name: The name of the snapshot's folder (usually the snapshot ID).
            catalogue_path: The base path of the snapshot catalogue.

        Returns:
            The full path to the snapshot's directory.
        """
        return catalogue_path.joinpath(folder_name)

    @staticmethod
    def get_snapshot_json_path(folder_name: str, catalogue_path: Path, json_filename: str) -> Path:
        """
        Constructs the full path to a snapshot's JSON file.

        Args:
            folder_name: The name of the snapshot's folder.
            catalogue_path: The base path of the snapshot catalogue.
            json_filename: The name of the JSON file.

        Returns:
            The full path to the snapshot's JSON file.
        """
        return SnapshotUtils.get_snapshot_path(folder_name, catalogue_path).joinpath(json_filename)

    @staticmethod
    def get_edits_between_snapshots(old: Snapshot, new: Snapshot) -> list[SnapEditAction]:
        """
        Compares two Snapshot objects and generates a list of actions (add/remove)
        required to transform the old snapshot into the new one.

        Args:
            old: The original Snapshot object.
            new: The updated Snapshot object.

        Returns:
            A list of SnapEditAction objects representing the changes.
        """
        edits: list[SnapEditAction] = []

        old_path_to_assoc = {dir_assoc.original_path: dir_assoc for dir_assoc in old.directories}
        new_path_to_assoc = {dir_assoc.original_path: dir_assoc for dir_assoc in new.directories}

        old_paths = set(old_path_to_assoc.keys())
        new_paths = set(new_path_to_assoc.keys())

        # Find added folders (present in new but not in old)
        added_paths = new_paths - old_paths
        for path in added_paths:
            edits.append(SnapEditAction(
                action_type=SnapEditType.ADD_DIR,
                new_path=path
            ))

        # Find removed folders (present in old but not in new)
        removed_paths = old_paths - new_paths
        for path in removed_paths:
            assoc = old_path_to_assoc[path]
            edits.append(SnapEditAction(
                action_type=SnapEditType.REMOVE_DIR,
                folder_id_to_remove=assoc.folder_id,
                directory_name_to_remove=assoc.directory_name
            ))

        return edits

    @staticmethod
    def sort_snapshots(
        snapshots: list[Snapshot],
        sort_by: 'SnapshotSortKey',
        reverse: bool = False
    ) -> list[Snapshot]:
        """
        Sorts a list of Snapshot objects by a specified key.
        Snapshots with a None value for the key are placed at the end.
        String comparison is case-insensitive.

        Args:
            snapshots: The list of Snapshots to sort.
            sort_by: The key to sort by, as a SnapshotSortKey enum member.
            reverse: If True, sorts in descending order.

        Returns:
            A new list containing the sorted Snapshots.
        """
        key_attr = sort_by.value
        snaps_with_value = []
        snaps_with_none = []

        for snap in snapshots:
            if getattr(snap, key_attr) is None:
                snaps_with_none.append(snap)
            else:
                snaps_with_value.append(snap)

        def get_key(snapshot: Snapshot):
            value = getattr(snapshot, key_attr)
            if isinstance(value, str):
                return value.lower()
            return value

        sorted_snaps = sorted(snaps_with_value, key=get_key, reverse=reverse)

        return sorted_snaps + snaps_with_none




class SnapshotSerializer:

    @staticmethod
    def _converter(o):
        """
        Converts non-serializable objects for JSON dumping.

        Args:
            o: The object to convert.

        Returns:
            A serializable representation of the object.

        Raises:
            TypeError: If the object type is not supported.
        """
        if isinstance(o, datetime):
            return o.isoformat()
        if isinstance(o, Enum):
            return o.value  # or o.name if you prefer the name
        raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")

    @staticmethod
    def to_json(snapshot: Snapshot, path: Path) -> None:
        """
        Serializes a Snapshot object to a JSON file.

        Args:
            snapshot: The Snapshot object to serialize.
            path: The file path where the JSON data will be saved.
        """
        data_dict = asdict(snapshot)
        json_str = json.dumps(data_dict, default=SnapshotSerializer._converter, indent=4)
        path.write_text(json_str, encoding="utf-8")


    @classmethod
    def from_json(cls, filepath: Path) -> Snapshot:
        """Reads a Snapshot from a JSON file, converting datetimes and enums."""
        data = json.loads(filepath.read_text(encoding="utf-8"))

        # Convert datetime fields from ISO8601 string to datetime
        for key in ["date_created", "date_last_installed", "date_modified", "date_last_used", "date_last_modified"]:
            if key in data and data[key] is not None:
                data[key] = datetime.fromisoformat(data[key])

        # Convert 'directories' into a list of SnapDirAssociation
        if "directories" in data and isinstance(data["directories"], list):
            data["directories"] = [SnapDirAssociation(**d) if isinstance(d, dict) else d for d in data["directories"]]

        return Snapshot(**data)

    @classmethod
    def update_field(cls, filepath: Path, field_name: str, new_value):
        """
        Updates a single field in a snapshot's JSON file without loading the whole object.

        Args:
            filepath: The path to the JSON file.
            field_name: The name of the field to update.
            new_value: The new value for the field.
        """
        # Read existing data from the JSON file
        data = json.loads(filepath.read_text(encoding="utf-8"))

        # Update only the specified field
        data[field_name] = new_value

        # Serialize the file again with converters for datetime and enum if necessary
        json_str = json.dumps(data, default=cls._converter, indent=4)
        filepath.write_text(json_str, encoding="utf-8")



class SnapshotManager:

    def __init__(
            self,
            snapshot: Snapshot,
            catalogue_path: Path,
            settings: SnapshotSettings = SnapshotSettings(),
    ):
        """
        Initializes a manager for a single snapshot's lifecycle.

        Args:
            snapshot: The `Snapshot` object to manage.
            catalogue_path: The root path of the snapshot catalogue.
            settings: Configuration settings for the manager.
        """
        self.snapshot = snapshot
        self.settings = settings
        self.path_catalogue = catalogue_path
        self.path_snapshot = SnapshotUtils.get_snapshot_path(self.snapshot.folder_name, self.path_catalogue)
        self.path_snapshot_json = SnapshotUtils.get_snapshot_json_path(self.snapshot.folder_name, self.path_catalogue, self.settings.json_filename)

    def __save_json(self):
        """Saves the current snapshot object state to its JSON file."""
        SnapshotSerializer.to_json(self.snapshot, self.path_snapshot_json)

    def create(self):
        """
        Creates the snapshot on the filesystem. This involves creating the main snapshot
        directory and copying all associated directories into it. If the directory
        already exists, its contents are cleared first.
        """
        if self.path_snapshot.exists():
            clear_folder_contents(self.path_snapshot)
        self.path_snapshot.mkdir(parents=True, exist_ok=True)
        for snap_dir in self.snapshot.directories:
            snap_dir.copy_install_to(self.path_snapshot)
        self.__save_json()

    def delete(self):
        """
        Deletes the snapshot's directory from the filesystem.
        The directory is moved to a temporary location before being permanently deleted.
        """
        if self.path_snapshot.exists():
            clear_or_move_to_temp(self.path_snapshot)

    def update_json_data_fields(self):
        """
        Updates the 'data' and 'date_last_modified' fields in the snapshot's JSON file.
        This method is typically called after modifying the snapshot's data dictionary.
        """
        SnapshotSerializer.update_field(self.path_snapshot_json, "data", self.snapshot.data)
        SnapshotSerializer.update_field(self.path_snapshot_json, "date_last_modified", datetime.now().isoformat())
        self.snapshot.date_last_modified = datetime.now()

    def update_json_base_fields(self):
        """
        Updates the basic metadata fields (name, desc, author, tags, date_modified)
        of the snapshot's JSON file.
        """
        SnapshotSerializer.update_field(self.path_snapshot_json, "name", self.snapshot.name)
        SnapshotSerializer.update_field(self.path_snapshot_json, "desc", self.snapshot.desc)
        SnapshotSerializer.update_field(self.path_snapshot_json, "author", self.snapshot.author)
        SnapshotSerializer.update_field(self.path_snapshot_json, "tags", self.snapshot.tags)
        SnapshotSerializer.update_field(self.path_snapshot_json, "date_modified", datetime.now().isoformat())
        self.snapshot.date_modified = datetime.now()

    def install_directory(self, destination_path: Path):
        """
        Adds a new directory to the snapshot, copying its contents into the
        snapshot's storage directory.

        Args:
            destination_path: The path of the directory to add to the snapshot.
        
        Raises:
            ValueError: If the destination_path is not a valid directory.
        """
        if not destination_path.exists() or not destination_path.is_dir():
            raise ValueError(f"The provided path {destination_path} is not a valid directory.")
        new_dir = SnapDirAssociation(
            index=SnapDirAssociation.next_index(),
            original_path=destination_path.as_posix(),
            folder_id=gen_random_string(self.settings.folder_id_length)
        )
        new_dir.copy_install_to(self.path_snapshot)
        self.snapshot.directories.append(new_dir)
        self.__save_json()

    def uninstall_directory_by_folder_id(self, folder_id: str):
        """
        Removes a directory from the snapshot based on its folder_id.
        This deletes the directory's copy from the snapshot's storage and updates the JSON file.

        Args:
            folder_id: The unique ID of the folder to remove.
        """
        dir_to_remove = next((d for d in self.snapshot.directories if d.folder_id == folder_id), None)
        if dir_to_remove:
            dir_path = self.path_snapshot.joinpath(dir_to_remove.directory_name)
            if dir_path.exists():
                clear_or_move_to_temp(dir_path)
            self.snapshot.directories.remove(dir_to_remove)
            self.__save_json()

    def update_from_actions_list(self, edits: list[SnapEditAction]):
        """
        Applies a list of edit actions (add/remove directories) to the snapshot.
        This updates the snapshot's contents on the filesystem based on the provided actions.

        Args:
            edits: A list of SnapEditAction objects.
        """
        # The `self.snapshot` is the NEW snapshot.

        # Handle additions
        add_actions = [e for e in edits if e.action_type == SnapEditType.ADD_DIR]
        added_paths = {e.new_path for e in add_actions}

        for dir_assoc in self.snapshot.directories:
            # Find the newly added directories in the snapshot's list
            # The path in dir_assoc is already normalized by __post_init__
            if dir_assoc.original_path in added_paths:
                # This is a new directory. Copy its content to the snapshot storage.
                dir_assoc.copy_install_to(self.path_snapshot)

        # Handle removals
        remove_actions = [e for e in edits if e.action_type == SnapEditType.REMOVE_DIR]
        for edit in remove_actions:
            if edit.directory_name_to_remove:
                dir_path = self.path_snapshot.joinpath(edit.directory_name_to_remove)
                if dir_path.exists():
                    clear_or_move_to_temp(dir_path)

        # After all filesystem changes, save the final state of the new snapshot.
        self.__save_json()

    def duplicate(self):
        """
        Creates a duplicate of the current snapshot with a new ID and name.
        The entire snapshot directory is copied, and a new JSON file is created for the copy.

        Raises:
            FileNotFoundError: If the original snapshot path does not exist.
        """
        if not self.path_snapshot.exists():
            raise FileNotFoundError(f"The snapshot path {self.path_snapshot} does not exist.")
        new_snap = self.snapshot
        new_snap.id = gen_random_string(self.settings.snap_id_length)
        new_snap.name = self.snapshot.name + " Copy"
        new_snap.date_created = datetime.now()
        new_snap_path = SnapshotUtils.get_snapshot_path(new_snap.folder_name, self.path_catalogue)
        new_snap_json_path = SnapshotUtils.get_snapshot_json_path(new_snap.folder_name, self.path_catalogue, self.settings.json_filename)
        duplicate_directory(self.path_snapshot, new_snap_path, "")
        SnapshotSerializer.to_json(new_snap, new_snap_json_path)

    def update_associated_dirs_from_system(self):
        """
        Updates the snapshot's internal copy of each associated directory
        with the current version from the original system path.
        """
        for dir_assoc in self.snapshot.directories:
            snapshot_copy_path = self.path_snapshot / dir_assoc.directory_name
            system_path = Path(dir_assoc.original_path)

            if snapshot_copy_path.exists():
                shutil.rmtree(snapshot_copy_path)
            
            if system_path.exists() and system_path.is_dir():
                dir_assoc.copy_install_to(self.path_snapshot)
                dir_assoc.mb_size = get_folder_size_mb(system_path)
            else:
                dir_assoc.mb_size = 0.0
                logger.warning(f"Original path '{system_path}' for snapshot '{self.snapshot.id}' does not exist. The snapshot's copy has been cleared.")

        self.snapshot.date_last_modified = datetime.now()
        self.__save_json()

    def remove_installed_copies(self):
        """
        Removes all directories on the system that this snapshot is managing.
        This is effectively an 'uninstall' operation for the snapshot's associated directories.
        It only removes the copies at the 'original_path' locations, not the snapshot's
        internal backup.
        """
        for dir_assoc in self.snapshot.directories:
            install_path = Path(dir_assoc.original_path)
            if install_path.exists() and install_path.is_dir():
                logger.info(f"Removing installed copy at '{install_path}'")
                try:
                    shutil.rmtree(install_path)
                except Exception as e:
                    logger.error(f"Failed to remove directory '{install_path}': {e}")
            else:
                logger.debug(f"Install path '{install_path}' does not exist or is not a directory. Skipping.")

    def install(self, enable_everyone_full_control: bool = True):
        """
        Installs the snapshot's contents to their original locations on the filesystem.
        This will clear the destination directories before copying the snapshot's contents.

        Args:
            enable_everyone_full_control (bool): If True and on Windows, it will attempt
                to set full control permissions for the 'Everyone' group on the
                installed directories.
        """
        import sys
        if sys.platform == 'win32':
            try:
                import win32security
                import ntsecuritycon as con
            except ImportError:
                logger.error("pywin32 not installed, cannot set file permissions.")
                win32security = None
        else:
            win32security = None

        for dir_assoc in self.snapshot.directories:
            source_dir = self.path_snapshot.joinpath(dir_assoc.directory_name)
            install_location = Path(dir_assoc.original_path)

            logger.info(f"Performing clean installation from '{source_dir}' to '{install_location}'")

            # 1. Ensure the destination directory exists.
            install_location.mkdir(parents=True, exist_ok=True)

            # 2. Clear the contents of the destination directory.
            logger.info(f"Clearing contents of '{install_location}' before install.")
            for item in install_location.iterdir():
                try:
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
                except Exception as e:
                    logger.error(f"Could not remove item {item} during clean install: {e}")

            # 3. Copy the contents from the source directory to the now-empty destination.
            for item in source_dir.iterdir():
                src_item = source_dir / item.name
                dst_item = install_location / item.name
                try:
                    if src_item.is_dir():
                        shutil.copytree(src_item, dst_item)
                    else:
                        shutil.copy2(src_item, dst_item)
                except Exception as e:
                    logger.error(f"Could not copy item {src_item} during install: {e}")

            # 4. Set permissions if on Windows and pywin32 is installed
            if win32security:
                try:
                    logger.info(f"Setting full control permissions for Everyone on '{install_location}'")

                    everyone, domain, type = win32security.LookupAccountName("", "Everyone")

                    sd = win32security.GetFileSecurity(str(install_location), win32security.DACL_SECURITY_INFORMATION)
                    dacl = sd.GetSecurityDescriptorDacl()

                    dacl.AddAccessAllowedAceEx(
                        win32security.ACL_REVISION,
                        con.OBJECT_INHERIT_ACE | con.CONTAINER_INHERIT_ACE,
                        con.GENERIC_ALL,
                        everyone
                    )

                    sd.SetSecurityDescriptorDacl(1, dacl, 0)
                    win32security.SetFileSecurity(str(install_location), win32security.DACL_SECURITY_INFORMATION, sd)

                except Exception as e:
                    logger.error(f"Failed to set permissions on '{install_location}': {e}")

        self.snapshot.date_last_used = datetime.now()
        SnapshotSerializer.update_field(self.path_snapshot_json, "date_last_used", self.snapshot.date_last_used.isoformat())

    def create_backup(self, backup_path: Path, prefix: str, backup_type: 'BackupType', is_export: bool = False):
        """
        Creates a zip archive of the snapshot's data.

        Args:
            backup_path: The directory where the backup zip file will be saved.
            prefix: A prefix for the backup filename.
            backup_type: The type of backup to create (associated directories or the snapshot directory).
            is_export: If True, the filename will be formatted as an export.
        """
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            backup_type_suffix = ""
            if backup_type == BackupType.ASSOCIATED_DIRECTORIES:
                backup_type_suffix = "_ad"
            elif backup_type == BackupType.SNAPSHOT_DIRECTORY:
                backup_type_suffix = "_sd"

            if is_export:
                zip_name = f"{prefix}_{self.snapshot.id}{backup_type_suffix}_{timestamp}.zip"
            else:
                zip_name = f"backup_{prefix}_{self.snapshot.id}{backup_type_suffix}_{timestamp}.zip"
            
            backup_path.mkdir(parents=True, exist_ok=True)
            zip_path = backup_path.joinpath(zip_name)

            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
                if backup_type == BackupType.ASSOCIATED_DIRECTORIES:
                    dirs_to_backup = [Path(d.original_path) for d in self.snapshot.directories]
                    for folder in dirs_to_backup:
                        if folder.is_dir():
                            for file_path in folder.rglob("*"):
                                if file_path.is_file():
                                    archive.write(
                                        file_path,
                                        arcname=os.path.join(folder.name, file_path.relative_to(folder))
                                    )
                elif backup_type == BackupType.SNAPSHOT_DIRECTORY:
                    source_dir = self.path_snapshot
                    for file_path in source_dir.rglob("*"):
                        if file_path.is_file():
                            archive.write(
                                file_path,
                                arcname=file_path.relative_to(source_dir)
                            )
        except Exception as e:
            logger.error(e)


class SnapshotCatalogue:

    def __init__(
            self,
            path_catalogue: Path,
            settings: SnapshotSettings = SnapshotSettings(),
    ):
        """
        Initializes the catalogue manager for a collection of snapshots.

        Args:
            path_catalogue: The root directory path for the catalogue.
            settings: Global settings to apply to snapshots in this catalogue.
        """
        self.path_catalogue = path_catalogue
        self.settings = settings
        self.path_catalogue.mkdir(parents=True, exist_ok=True)

    def set_catalogue_path(self, new_path: Path):
        """
        Sets a new path for the snapshot catalogue.
        The directory will be created if it does not exist.

        Args:
            new_path: The new path for the catalogue.
        """
        self.path_catalogue = new_path
        self.path_catalogue.mkdir(parents=True, exist_ok=True)

    def add(self, snap: Snapshot):
        """
        Adds a new snapshot to the catalogue.

        Args:
            snap: The Snapshot object to add.
        """
        snap_manager = SnapshotManager(snap, self.path_catalogue, self.settings)
        snap_manager.create()

    def delete(self, snap: Snapshot):
        """
        Deletes a snapshot from the catalogue.

        If backup settings are enabled, a backup is created before deletion.

        Args:
            snap: The Snapshot object to delete.
        """
        snap_manager = SnapshotManager(snap, self.path_catalogue, self.settings)
        if self.settings.bck_before_delete_enabled:
            snap_manager.create_backup(self.settings.backup_path, "beforeDelete", BackupType.SNAPSHOT_DIRECTORY)
        snap_manager.delete()

    def get_all(self) -> list[Snapshot]:
        """
        Retrieves all snapshots from the catalogue.

        Returns:
            A list of Snapshot objects found in the catalogue.
        """
        self.path_catalogue.mkdir(parents=True, exist_ok=True)
        snapshots: list[Snapshot] = []
        for current_dir in self.path_catalogue.iterdir():
            if current_dir.is_dir():
                snap = SnapshotUtils.get_snapshot_from_path(current_dir, self.settings.json_filename)
                if snap is not None:
                    snapshots.append(snap)
        return snapshots

    def get_by_id(self, snap_id: str) -> Optional[Snapshot]:
        """
        Retrieves a single snapshot from the catalogue by its ID.

        Args:
            snap_id: The ID of the snapshot to retrieve.

        Returns:
            The Snapshot object if found, otherwise None.
        """
        all_snaps = self.get_all()
        for snap in all_snaps:
            if snap.id == snap_id:
                return snap
        return None

    def update_snapshot_by_objs(self, old: Snapshot, new: Snapshot):
        """
        Updates a snapshot by comparing the old and new Snapshot objects.
        It calculates the differences and applies them.

        Args:
            old: The original Snapshot object.
            new: The new Snapshot object with the desired changes.
        """
        edits = SnapshotUtils.get_edits_between_snapshots(old, new)
        self.update_snapshot_by_edits(new, edits)

    def update_snapshot_by_edits(self, snap: Snapshot, edits: list[SnapEditAction]):
        """
        Updates a snapshot using a pre-computed list of edit actions.

        If backup settings are enabled, a backup is created before the update.

        Args:
            snap: The Snapshot object to update.
            edits: A list of SnapEditAction objects to apply.
        """
        snap_manager = SnapshotManager(snap, self.path_catalogue, self.settings)
        if self.settings.bck_before_modify_enabled:
            snap_manager.create_backup(self.settings.backup_path, "beforeEdit", BackupType.SNAPSHOT_DIRECTORY)
        snap_manager.update_json_base_fields()
        snap_manager.update_json_data_fields()
        snap_manager.update_from_actions_list(edits)

    def duplicate_by_id(self, snap_id: str):
        """
        Duplicates a snapshot by its ID.

        Args:
            snap_id: The ID of the snapshot to duplicate.

        Raises:
            ValueError: If no snapshot is found with the given ID.
        """
        snap = self.get_by_id(snap_id)
        if snap is None:
            raise ValueError(f"No snapshot found with ID {snap_id}")
        snap_manager = SnapshotManager(snap, self.path_catalogue, self.settings)
        snap_manager.duplicate()

    def export_assoc_dirs(self, snap_id: str, destination_path: Path):
        """
        Exports the associated directories of a snapshot to a zip file.

        Args:
            snap_id: The ID of the snapshot to export.
            destination_path: The folder where the exported zip file will be saved.
        """
        snap = self.get_by_id(snap_id)
        if not snap:
            raise ValueError(f"No snapshot found with ID {snap_id}")

        snap_manager = SnapshotManager(snap, self.path_catalogue, self.settings)
        # Use the existing create_backup method with a specific prefix for export
        snap_manager.create_backup(destination_path, "export", BackupType.ASSOCIATED_DIRECTORIES, is_export=True)

    def export_snapshot(self, snap_id: str, destination_path: Path):
        """
        Exports the entire snapshot directory (the internal backup) to a zip file.

        Args:
            snap_id: The ID of the snapshot to export.
            destination_path: The folder where the exported zip file will be saved.
        """
        snap = self.get_by_id(snap_id)
        if not snap:
            raise ValueError(f"No snapshot found with ID {snap_id}")

        snap_manager = SnapshotManager(snap, self.path_catalogue, self.settings)
        snap_manager.create_backup(destination_path, "export_snap", BackupType.SNAPSHOT_DIRECTORY, is_export=True)

    def export_catalogue(self, destination_path: Path, file_name: str = "catalogue_export.zip"):
        """
        Exports the entire catalogue to a single zip file.

        Args:
            destination_path: The folder where the exported zip file will be saved.
            file_name: The name for the output zip file.
        """
        destination_path.mkdir(parents=True, exist_ok=True)
        zip_path = destination_path.joinpath(file_name)
        
        snapshots = self.get_all()
        if not snapshots:
            logger.warning("Catalogue is empty. Nothing to export.")
            return

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for snap in snapshots:
                snap_dir = self.get_snap_directory_path(snap)
                if snap_dir and snap_dir.is_dir():
                    for file_path in snap_dir.rglob("*"):
                        if file_path.is_file():
                            archive.write(
                                file_path,
                                arcname=file_path.relative_to(self.path_catalogue)
                            )

    def import_catalogue(self, zip_path: Path):
        """
        Imports all snapshots from a catalogue zip file, skipping existing ones.

        Args:
            zip_path: The path to the catalogue .zip file.

        Raises:
            ValueError: If the provided path is not a valid .zip file.
            IOError: If the zip file fails to extract.
        """
        if not zip_path.is_file() or zip_path.suffix != '.zip':
            raise ValueError(f"Provided path '{zip_path}' is not a valid .zip file.")

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)

            # 1. Extract the zip to a temporary directory
            try:
                with zipfile.ZipFile(zip_path, 'r') as zf:
                    zf.extractall(temp_dir_path)
            except zipfile.BadZipFile:
                raise ValueError(f"File '{zip_path}' is not a valid zip file.")
            except Exception as e:
                raise IOError(f"Failed to extract zip file '{zip_path}': {e}")

            # 2. Iterate through extracted folders and import them
            for potential_snap_dir in temp_dir_path.iterdir():
                if not potential_snap_dir.is_dir():
                    continue

                json_path = potential_snap_dir / self.settings.json_filename
                if not json_path.is_file():
                    logger.warning(f"Skipping directory '{potential_snap_dir.name}' as it does not contain a snapshot json file.")
                    continue

                try:
                    # Read just the ID to avoid loading the whole object unnecessarily
                    data = json.loads(json_path.read_text(encoding="utf-8"))
                    snap_id = data.get("id")
                    if not snap_id:
                        logger.warning(f"Skipping directory '{potential_snap_dir.name}' as snapshot ID is missing from json.")
                        continue

                    # 3. Check for ID conflict
                    if self.exists(snap_id):
                        logger.info(f"Snapshot with ID '{snap_id}' already exists. Skipping import.")
                        continue

                    # 4. Copy the extracted folder to the catalogue
                    destination_path = self.path_catalogue / snap_id
                    shutil.copytree(potential_snap_dir, destination_path)
                    logger.info(f"Successfully imported snapshot with ID '{snap_id}'.")

                except Exception as e:
                    logger.error(f"Failed to import snapshot from directory '{potential_snap_dir.name}': {e}")

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
        if not zip_path.is_file() or zip_path.suffix != '.zip':
            raise ValueError(f"Provided path '{zip_path}' is not a valid .zip file.")

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)

            # 1. Extract the zip to a temporary directory
            try:
                with zipfile.ZipFile(zip_path, 'r') as zf:
                    zf.extractall(temp_dir_path)
            except zipfile.BadZipFile:
                raise ValueError(f"File '{zip_path}' is not a valid zip file.")
            except Exception as e:
                raise IOError(f"Failed to extract zip file '{zip_path}': {e}")

            # 2. Validate the content and get snapshot
            json_path = temp_dir_path / self.settings.json_filename
            if not json_path.is_file():
                raise ValueError(f"The zip file does not contain a snapshot json file ('{self.settings.json_filename}').")

            try:
                snapshot_to_import = SnapshotSerializer.from_json(json_path)
            except Exception as e:
                raise ValueError(f"Failed to read snapshot data from json: {e}")

            # 3. Check for ID conflict
            if self.exists(snapshot_to_import.id):
                raise ValueError(f"A snapshot with the ID '{snapshot_to_import.id}' already exists in the catalogue.")

            # 4. Copy the extracted folder to the catalogue
            destination_path = self.path_catalogue / snapshot_to_import.id
            shutil.copytree(temp_dir_path, destination_path)

    def update_assoc_with_installed(self, snap_id: str):
        """
        Updates the snapshot's internal copy of associated directories
        with the current state of those directories on the filesystem.
        """
        snap = self.get_by_id(snap_id)
        if not snap:
            raise ValueError(f"No snapshot found with ID {snap_id}")

        snap_manager = SnapshotManager(snap, self.path_catalogue, self.settings)
        snap_manager.update_associated_dirs_from_system()

    def remove_installed_copies(self, snap_id: str):
        """
        Removes the installed copies of a snapshot's associated directories from the system.

        Args:
            snap_id: The ID of the snapshot whose installed copies should be removed.
        """
        snap = self.get_by_id(snap_id)
        if not snap:
            logger.warning(f"Snapshot with ID '{snap_id}' not found. Cannot remove installed copies.")
            return
        snap_manager = SnapshotManager(snap, self.path_catalogue, self.settings)
        snap_manager.remove_installed_copies()

    def install(self, snap: Snapshot):
        """
        Installs a snapshot's contents to their original target locations.

        If backup settings are enabled, a backup of the target locations is created first.

        Args:
            snap: The Snapshot object to install.
        """
        snap_manager = SnapshotManager(snap, self.path_catalogue, self.settings)
        if self.settings.bck_before_install_enabled:
            snap_manager.create_backup(self.settings.backup_path, "preinstall", BackupType.ASSOCIATED_DIRECTORIES)
        snap_manager.install(self.settings.install_with_everyone_full_control)

    def exists(self, snap_id: str) -> bool:
        """
        Checks if a snapshot with the given ID exists in the catalogue.

        Args:
            snap_id: The ID of the snapshot to check.

        Returns:
            True if the snapshot exists, False otherwise.
        """
        return self.get_by_id(snap_id) is not None

    def get_snap_directory_path(self, snap: Snapshot) -> Path | None:
        """
        Gets the filesystem path to a snapshot's storage directory.

        Args:
            snap: The Snapshot object.

        Returns:
            The Path to the snapshot's directory, or None if the snapshot doesn't exist.
        """
        if not self.exists(snap.id):
            return None
        return SnapshotUtils.get_snapshot_path(snap.folder_name, self.path_catalogue)


@dataclass
class SnapshotSearchResult:
    """
    Represents a single search result within a snapshot file.
    Can be a match in file content or a match of a file name.
    """
    file_path: Path
    searched_text: str
    snapshot_name: str
    line_number: Optional[int] = None
    line_content: Optional[str] = None


class QueryType(Enum):
    """Specifies whether a search query is plain text or a regular expression."""
    TEXT = "text"
    REGEX = "regex"


class SearchTarget(Enum):
    """Specifies whether to search for a file name or within file content."""
    FILE_NAME = "name"
    FILE_CONTENT = "content"


@dataclass
class SnapshotSearchParams:
    """
    Parameters for searching within a snapshot.
    """
    query: str
    search_target: SearchTarget = SearchTarget.FILE_CONTENT
    query_type: QueryType = QueryType.TEXT
    extensions: list[str] = field(default_factory=list)


class SnapshotSearcher:
    """
    Searches for textual content within the files of one or more snapshots.
    """
    def __init__(self, catalogue: SnapshotCatalogue):
        """
        Initializes the SnapshotSearcher.

        Args:
            catalogue: The SnapshotCatalogue to search in.
        """
        self.catalogue = catalogue

    def search(self, snapshot: Snapshot, params: SnapshotSearchParams, on_progress: Optional[SnapshotProgressCallback] = None) -> list[SnapshotSearchResult]:
        """
        Performs a search in a single snapshot based on the provided parameters.

        Args:
            snapshot: The `Snapshot` object to search within.
            params: An object containing the search query and options.
            on_progress: An optional callback function to report search progress,
                         receiving (filename, total_files, processed_files).

        Returns:
            A list of `SnapshotSearchResult` objects matching the query.
        """
        snapshot_path = self.catalogue.get_snap_directory_path(snapshot)

        compiled_regex = None
        if params.query_type == QueryType.REGEX:
            try:
                compiled_regex = re.compile(params.query)
            except re.error as e:
                logger.error(f"Invalid regex pattern provided: {e}")
                return []

        return self._search_in_snapshot_path(snapshot, snapshot_path, params, compiled_regex, on_progress)

    def search_list(self, snapshots: list[Snapshot], params: SnapshotSearchParams, on_progress: Optional[SnapshotProgressCallback] = None) -> list[SnapshotSearchResult]:
        """
        Performs a search across a list of snapshots based on the provided parameters.

        Args:
            snapshots: A list of Snapshot objects to search within.
            params: The search parameters (query, type, extensions).
            on_progress: An optional callback to report progress.

        Returns:
            A list of all search results found across all specified snapshots.
        """
        all_results: list[SnapshotSearchResult] = []
        for snapshot in snapshots:
            all_results.extend(self.search(snapshot, params, on_progress))
        return all_results

    def _search_in_snapshot_path(self, snapshot: Snapshot, snapshot_path: Path, params: SnapshotSearchParams, compiled_regex: Optional[re.Pattern], on_progress: Optional[SnapshotProgressCallback]) -> list[SnapshotSearchResult]:
        """
        Private helper to perform a search within a specific snapshot's directory path.

        Args:
            snapshot: The snapshot being searched.
            snapshot_path: The filesystem path of the snapshot's contents.
            params: The search parameters.
            compiled_regex: A pre-compiled regex pattern, if applicable.
            on_progress: The progress callback function.

        Returns:
            A list of search results found in the snapshot.
        """
        results: list[SnapshotSearchResult] = []
        if not snapshot_path or not snapshot_path.is_dir():
            logger.warning(f"Snapshot path '{snapshot_path}' for snapshot id '{snapshot.id}' does not exist or is not a directory.")
            return results

        # 1. Collect all files to be searched
        files_to_search: list[Path] = []
        for dir_assoc in snapshot.directories:
            copied_dir_path = snapshot_path.joinpath(dir_assoc.directory_name)
            if not copied_dir_path.is_dir():
                continue
            for file_path in copied_dir_path.rglob('*'):
                if self._should_search_file(file_path, params.extensions):
                    files_to_search.append(file_path)

        # 2. Iterate and report progress
        total_files = len(files_to_search)
        for i, file_path in enumerate(files_to_search):
            if on_progress:
                on_progress(file_path.name, total_files, i + 1)

            if params.search_target == SearchTarget.FILE_NAME:
                found = False
                if params.query_type == QueryType.TEXT:
                    if params.query in file_path.name:
                        found = True
                elif compiled_regex and compiled_regex.search(file_path.name):
                    found = True
                
                if found:
                    results.append(SnapshotSearchResult(
                        file_path=file_path,
                        searched_text=params.query,
                        snapshot_name=snapshot.name
                    ))
            
            elif params.search_target == SearchTarget.FILE_CONTENT:
                results.extend(self._search_in_file(file_path, params, compiled_regex, snapshot.name))

        return results


    def _should_search_file(self, file_path: Path, extensions: list[str]) -> bool:
        """
        Determines if a file should be included in the search.

        Args:
            file_path: The path to the file.
            extensions: A list of file extensions to include. If empty, all files are included.

        Returns:
            True if the file should be searched, False otherwise.
        """
        if not file_path.is_file():
            return False
        if not extensions:
            return True  # If no extensions are specified, search all files
        return file_path.suffix in extensions

    def _search_in_file(self, file_path: Path, params: SnapshotSearchParams, compiled_regex: Optional[re.Pattern], snapshot_name: str) -> list[SnapshotSearchResult]:
        """
        Performs the search within a single file.

        Args:
            file_path: The path of the file to search.
            params: The search parameters.
            compiled_regex: A pre-compiled regex pattern, if applicable.
            snapshot_name: The name of the snapshot for including in results.

        Returns:
            A list of search results found within the file.
        """
        results: list[SnapshotSearchResult] = []
        try:
            with file_path.open('r', encoding='utf-8') as f:
                for i, line in enumerate(f, 1):
                    found = False
                    if params.query_type == QueryType.TEXT:
                        if params.query in line:
                            found = True
                    elif compiled_regex and compiled_regex.search(line):
                        found = True

                    if found:
                        results.append(SnapshotSearchResult(
                            file_path=file_path,
                            searched_text=params.query,
                            line_number=i,
                            line_content=line.strip(),
                            snapshot_name=snapshot_name
                        ))
        except UnicodeDecodeError:
            logger.debug(f"Skipping binary file during search: {file_path}")
        except Exception as e:
            logger.warning(f"Error reading file {file_path} during search: {e}")
        return results