"""Snapshot value model and its metadata operations."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from pylizlib.core.os.snap.association_model import validate_directory_component

if TYPE_CHECKING:
    from pylizlib.core.os.snap.domain import SnapDirAssociation, Snapshot


class _SnapshotModel:
    """Represents a snapshot, which is a collection of directory associations
    and metadata at a specific point in time.

    Attributes:
        id (str): Non-empty snapshot ID used as one catalogue component under the library's existing component
            rules.
        name (str): Display name; it does not determine the stored directory component.
        desc (str): A description of the snapshot's purpose or contents.
        author (str): The user who created the snapshot.
        directories (list[SnapDirAssociation]): A list of `SnapDirAssociation` objects linking to the original
            directories.
        tags (list[str]): A list of strings for categorizing the snapshot.
        date_created (datetime): Creation datetime; the default is local naive datetime.now(), while supplied
            datetimes retain their timezone.
        date_modified (datetime | None): Last catalogue edit datetime or None; existing local/naive-compatible
            handling is retained.
        date_last_used (datetime | None): Last installed-use datetime or None; post-commit metadata errors expose
            whether its new value was published.
        date_last_modified (datetime | None): Last source synchronization datetime or None; library
            synchronization uses local datetime.now().
        os_created (str): Originating platform.system() label used to reject incompatible destructive operations.
        data (dict[str, str]): A dictionary for storing custom, arbitrary key-value data.
        capture_started_at (datetime | None): Timezone-aware acquisition start or None; library acquisitions use
            UTC.
        capture_completed_at (datetime | None): Timezone-aware acquisition completion or None; when both endpoints
            exist, completion cannot precede start.

    Notes:
        Construction validates contained associations and their path normalization. The model remains mutable and
        filesystem operations revalidate it. Association IDs and physical storage names must be unique; tags and
        custom data are strings. Capture endpoints must be timezone-aware, while other dates retain legacy
        datetime handling.
    """

    def __post_init__(self):
        """Validate a new mutable snapshot and every contained association.

        Returns:
            None: No return value.
        """
        self.validate()

    def validate(self) -> None:
        """Validate snapshot metadata, including every association used for paths.

        Returns:
            None: No return value.

        Raises:
            TypeError: An argument or mutable model field has a type rejected by this contract.
            ValueError: A value, path, resource limit or metadata field violates the validation rules described above.
        """

        # Check textual identity before it can influence any stored path.
        for name in ("id", "name", "desc", "author", "os_created"):
            if not isinstance(getattr(self, name), str):
                raise TypeError(f"Snapshot {name} must be a string.")
        if not self.id:
            raise ValueError("Snapshot ID cannot be empty.")
        validate_directory_component(self.id, "Snapshot ID")

        # Retain legacy datetime handling while requiring aware acquisition intervals.
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

        # Validate association models before enforcing unique stored names and stable IDs.
        from pylizlib.core.os.snap.domain import SnapDirAssociation

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

        # Validate extension data without converting or silently dropping user fields.
        if not isinstance(self.tags, list) or any(not isinstance(tag, str) for tag in self.tags):
            raise TypeError("Snapshot tags must be a list of strings.")
        if not isinstance(self.data, dict) or any(not isinstance(key, str) or not isinstance(value, str) for key, value in self.data.items()):
            raise TypeError("Snapshot data must be a dictionary of strings.")

    @property
    def tags_as_string(self) -> str:
        """Returns the list of tags as a single, comma-separated string.

        Returns:
            str: Sorted tags joined by comma-space, or one space when tags is empty.
        """
        return ", ".join(sorted(self.tags)) if self.tags else " "

    def get_for_table_array(self, key_list: list[str]) -> list[str]:
        """Generates a list of strings representing the snapshot's data for table display.

        Args:
            key_list (list[str]): A list of keys to retrieve from the snapshot's data dictionary.

        Returns:
            list[str]: Name, description, requested data values, date_created formatted as DD/MM/YYYY HH:MM:SS, and tags_as_string, in that order.
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
        """The name of the snapshot's folder in the catalogue, which is its ID.

        Returns:
            str: Snapshot ID used as its catalogue-directory component.
        """
        return self.id

    @property
    def get_assoc_dir_mb_size(self) -> float:
        """Returns the sum of the mb_size of all associated directories.

        Returns:
            float: Sum of known captured association sizes in MiB; unknown values are omitted and an empty sum is
                zero.
        """
        return sum(d.mb_size for d in self.directories if d.mb_size is not None)

    def add_data_item(self, key: str, value: str) -> None:
        """Adds a key-value pair to the custom data dictionary.

        Args:
            key (str): The key for the data item.
            value (str): The value to store.

        Returns:
            None: No return value.
        """
        self.data[key] = value

    def remove_data_item(self, key: str) -> Optional[str]:
        """Removes an item from the data dictionary and returns its value.

        Args:
            key (str): The key of the item to remove.

        Returns:
            Optional[str]: The value of the removed item, or None if the key was not found.
        """
        return self.data.pop(key, None)

    def has_data_item(self, key: str) -> bool:
        """Checks if a key exists in the data dictionary.

        Args:
            key (str): The key to check.

        Returns:
            bool: True if the key exists, False otherwise.
        """
        return key in self.data

    def get_data_item(self, key: str, default: str = "") -> str:
        """Gets a value from the data dictionary, returning a default if the key is not found.

        Args:
            key (str): The key of the item to retrieve.
            default (str): The default value to return if the key is not found.

        Returns:
            str: The value associated with the key, or the default value.
        """
        return self.data.get(key, default)

    def clear_all_data(self) -> None:
        """Clears all items from the data dictionary.

        Returns:
            None: No return value.
        """
        self.data.clear()

    def edit_data_item(self, key: str, new_value: str) -> None:
        """Edits the value of an existing item in the data dictionary.

        Args:
            key (str): The key of the item to edit.
            new_value (str): The new value to set.

        Returns:
            None: No return value.

        Raises:
            KeyError: If the key does not exist in the data dictionary.
        """
        if key in self.data:
            self.data[key] = new_value
        else:
            raise KeyError(f"Key '{key}' not found in data.")

    def clone(self) -> "Snapshot":
        """Creates a deep, independent copy of the Snapshot instance.

        Returns:
            Snapshot: A new `Snapshot` object with the same data as the original.
        """
        from pylizlib.core.os.snap.domain import Snapshot

        return Snapshot(
            id=self.id,
            name=self.name,
            desc=self.desc,
            author=self.author,
            directories=[self._clone_association(dir_assoc) for dir_assoc in self.directories],
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
        """Clone all association metadata while retaining its stable storage path.

        Args:
            dir_assoc (SnapDirAssociation): Directory association whose stored contents or installed copy is operated
                on.

        Returns:
            SnapDirAssociation: Independent association metadata retaining the same stable physical storage name.
        """
        from pylizlib.core.os.snap.domain import SnapDirAssociation

        clone = SnapDirAssociation(
            index=dir_assoc.index,
            original_path=dir_assoc.original_path,
            folder_id=dir_assoc.folder_id,
            mb_size=dir_assoc.mb_size,
            integrity_manifest=({path: dict(entry) for path, entry in dir_assoc.integrity_manifest.items()} if dir_assoc.integrity_manifest is not None else None),
        )
        clone._set_storage_name(dir_assoc.directory_name)
        return clone
