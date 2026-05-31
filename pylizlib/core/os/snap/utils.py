"""
Stateless utility functions for working with Snapshot objects.

Responsibilities (Single Responsibility Principle):
    - Generating random Snapshot instances for testing.
    - Loading a Snapshot from a filesystem path.
    - Building filesystem paths for snapshots and their JSON files.
    - Computing the diff (edit actions) between two Snapshot versions.
    - Sorting lists of Snapshot objects.

Classes:
    SnapshotUtils – Static helper methods for Snapshot operations.
"""

from pathlib import Path
from typing import Optional

from pylizlib.core.data.gen import gen_random_string
from pylizlib.core.os.snap.domain import (
    Snapshot,
    SnapDirAssociation,
    SnapEditAction,
    SnapEditType,
    SnapshotSortKey,
)
from pylizlib.core.os.snap.serializer import SnapshotSerializer


class SnapshotUtils:
    @staticmethod
    def gen_random_snap(source_folder_for_choices: Path, id_length: int = 10) -> Snapshot:
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
            edits.append(SnapEditAction(action_type=SnapEditType.ADD_DIR, new_path=path))

        # Find removed folders (present in old but not in new)
        removed_paths = old_paths - new_paths
        for path in removed_paths:
            assoc = old_path_to_assoc[path]
            edits.append(
                SnapEditAction(
                    action_type=SnapEditType.REMOVE_DIR,
                    folder_id_to_remove=assoc.folder_id,
                    directory_name_to_remove=assoc.directory_name,
                )
            )

        return edits

    @staticmethod
    def sort_snapshots(
        snapshots: list[Snapshot],
        sort_by: "SnapshotSortKey",
        reverse: bool = False,
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
