"""Legacy static entry points delegating to cohesive snapshot helper modules."""

from collections.abc import Iterable, Iterator
from pathlib import Path

import pylizlib.core.os.snap.diff as _diff
import pylizlib.core.os.snap.factories as _factories
import pylizlib.core.os.snap.sorting as _sorting
import pylizlib.core.os.snap.storage.archives as _storage_archives
import pylizlib.core.os.snap.storage.metadata as _storage_metadata
import pylizlib.core.os.snap.storage.paths as _storage_paths
import pylizlib.core.os.snap.storage.publication as _storage_publication
import pylizlib.core.os.snap.storage.tree as _storage_tree
from pylizlib.core.os.snap.copy_strategy import DirectoryCopyStrategy
from pylizlib.core.os.snap.domain import (
    SnapEditAction,
    Snapshot,
    SnapshotSortKey,
)
from pylizlib.core.os.snap.storage.tree import is_link_or_junction


class SnapshotUtils:
    """Compatibility facade for helpers now grouped by their actual responsibility.

    Use storage modules, diff, sorting and factories for internal implementation.
    Existing callers can retain these static entry points and signatures.
    """

    @staticmethod
    def _is_link_or_junction(path: Path) -> bool:
        """Retain the legacy entry point for the shared symlink/junction check.

        Args:
            path (Path): Native filesystem entry operated on by this method.

        Returns:
            bool: Whether the entry is a symbolic link or Windows junction, including a dangling link.
        """
        return is_link_or_junction(path)

    @staticmethod
    def iter_files_strict(root: Path) -> Iterator[Path]:
        """Enumerate regular files, rejecting links and propagating scan errors.

        Args:
            root (Path): Root directory for the tree operation; link and existence policy is described above.

        Returns:
            Iterator[Path]: Regular-file paths in existing traversal order; links and scan errors are not silently
                skipped.
        """
        return _storage_tree.iter_files_strict(root)

    @staticmethod
    def write_verified_zip(zip_path: Path, files: Iterable[tuple[Path, Path]], message_callback=None) -> Path:
        """Publish an archive only after complete enumeration and CRC verification.

        Args:
            zip_path (Path): ZIP archive path to read or publish, according to the operation.
            files (Iterable[tuple[Path, Path]]): Iterable of (source entry, relative archive name) pairs, enumerated
                fully before ZIP staging.
            message_callback (MessageCallback | None): Optional status observer receiving one message string; its
                exceptions propagate according to the calling operation.

        Returns:
            Path: Publish an archive only after complete enumeration and CRC verification.
        """
        return _storage_archives.write_verified_zip(zip_path, files, message_callback)

    @staticmethod
    def cleanup_after_commit(paths: Iterable[Path], operation: str) -> None:
        """Remove transaction leftovers without rolling back committed data.

        Cleanup may have already deleted part of a backup when it fails, so
        that backup must never be used for rollback. Log each failure and
        continue cleaning the remaining paths.

        Args:
            paths (Iterable[Path]): Ordered filesystem entries to inspect or clean up under the calling policy.
            operation (str): Operation name selecting recovery policy or identifying the operation in diagnostics.

        Returns:
            None: No return value.
        """
        return _storage_publication.cleanup_after_commit(paths, operation)

    @staticmethod
    def assert_no_symlinks(root: Path) -> None:
        """Reject symlinks and junctions anywhere in a tree before traversing it.

        Args:
            root (Path): Root directory for the tree operation; link and existence policy is described above.

        Returns:
            None: No return value.
        """
        return _storage_tree.assert_no_symlinks(root)

    @staticmethod
    def publish_snapshot_tree(
        source: Path,
        snapshot_id: str,
        catalogue_path: Path,
        *,
        replace_existing: bool = False,
        prepare_staging=None,
        copy_strategy: DirectoryCopyStrategy | None = None,
        message_callback=None,
        operation: str = "Snapshot copy",
    ) -> Path:
        """Copy to private staging, validate it, then publish with directory renames.

        Args:
            source (Path): Source file or directory whose contents or metadata are read.
            snapshot_id (str): Snapshot ID expected in metadata and used for the destination directory.
            catalogue_path (Path): Catalogue directory containing snapshot ID subdirectories.
            replace_existing (bool): Allow an existing snapshot ID to be replaced when True; otherwise collisions are
                rejected.
            prepare_staging (Callable[[Path], None] | None): Optional hook receiving the complete staging tree before
                publication; errors abort and trigger existing rollback.
            copy_strategy (DirectoryCopyStrategy | None): Directory-copy strategy; None selects the sequential default
                where supported.
            message_callback (MessageCallback | None): Optional status observer receiving one message string; its
                exceptions propagate according to the calling operation.
            operation (str): Operation name selecting recovery policy or identifying the operation in diagnostics.

        Returns:
            Path: Published catalogue snapshot path after staging and journal-driven directory renames.
        """
        return _storage_publication.publish_snapshot_tree(
            source, snapshot_id, catalogue_path, replace_existing=replace_existing, prepare_staging=prepare_staging, copy_strategy=copy_strategy, message_callback=message_callback, operation=operation
        )

    @staticmethod
    def gen_random_snap(source_folder_for_choices: Path, id_length: int = 10) -> Snapshot:
        """Generates a random Snapshot instance for testing or demonstration purposes.

        Args:
            source_folder_for_choices (Path): The path to a directory from which to pick random subdirectories.
            id_length (int): The length of the random string to be used for the snapshot's ID and name.

        Returns:
            Snapshot: A new Snapshot object with randomly generated data.
        """
        return _factories.gen_random_snap(source_folder_for_choices, id_length)

    @staticmethod
    def get_snapshot_from_path(path_snapshot: Path, json_filename: str) -> Snapshot | None:
        """Loads a Snapshot object from a directory containing a snapshot JSON file.

        Args:
            path_snapshot (Path): The path to the snapshot's directory.
            json_filename (str): The name of the JSON file that contains the snapshot's data.

        Returns:
            Snapshot: Decoded snapshot on success; missing paths/JSON and parsing/validation failures raise instead of
                returning None.

        Raises:
            ValueError: If the provided path is a file, not a directory.
            FileNotFoundError: If the path or the JSON file does not exist.

        Notes:
            This loader raises on missing paths or invalid JSON/domain data. Its historical optional return annotation
            is retained for API compatibility; it does not convert those failures to None.
        """
        return _storage_metadata.get_snapshot_from_path(path_snapshot, json_filename)

    @staticmethod
    def get_snapshot_path(folder_name: str, catalogue_path: Path) -> Path:
        """Constructs the full path to a snapshot's directory within the catalogue.
        Validates the folder name to prevent path traversal.

        Args:
            folder_name (str): The name of the snapshot's folder (usually the snapshot ID).
            catalogue_path (Path): The base path of the snapshot catalogue.

        Returns:
            Path: The full path to the snapshot's directory.

        Raises:
            ValueError: If the folder_name attempts path traversal or is invalid.
        """
        return _storage_paths.get_snapshot_path(folder_name, catalogue_path)

    @staticmethod
    def validate_snapshot_root(folder_name: str, catalogue_path: Path) -> Path:
        """Return the snapshot root, rejecting a root replaced by a symlink.

        Args:
            folder_name (str): Snapshot ID used as a single catalogue-directory component.
            catalogue_path (Path): Catalogue directory containing snapshot ID subdirectories.

        Returns:
            Path: Contained snapshot directory path, rejecting a root currently replaced by a link.
        """
        return _storage_paths.validate_snapshot_root(folder_name, catalogue_path)

    @staticmethod
    def get_snapshot_child_path(folder_name: str, catalogue_path: Path, child_name: str) -> Path:
        """Resolve and contain a single child path beneath its snapshot root.

        Args:
            folder_name (str): Snapshot ID used as a single catalogue-directory component.
            catalogue_path (Path): Catalogue directory containing snapshot ID subdirectories.
            child_name (str): Single direct-child component to resolve below the validated snapshot root.

        Returns:
            Path: Validated direct child path with no current link escape from the stored root.
        """
        return _storage_paths.get_snapshot_child_path(folder_name, catalogue_path, child_name)

    @staticmethod
    def get_snapshot_json_path(folder_name: str, catalogue_path: Path, json_filename: str) -> Path:
        """Constructs the full path to a snapshot's JSON file.

        Args:
            folder_name (str): The name of the snapshot's folder.
            catalogue_path (Path): The base path of the snapshot catalogue.
            json_filename (str): The name of the JSON file.

        Returns:
            Path: The full path to the snapshot's JSON file.
        """
        return _storage_paths.get_snapshot_json_path(folder_name, catalogue_path, json_filename)

    @staticmethod
    def get_edits_between_snapshots(old: Snapshot, new: Snapshot) -> list[SnapEditAction]:
        """Compares associations by stable folder_id and generates add/remove/rename actions
        required to transform the old snapshot into the new one.

        Args:
            old (Snapshot): The original Snapshot object.
            new (Snapshot): The updated Snapshot object.

        Returns:
            list[SnapEditAction]: A list of SnapEditAction objects representing the changes.
        """
        return _diff.get_edits_between_snapshots(old, new)

    @staticmethod
    def sort_snapshots(
        snapshots: list[Snapshot],
        sort_by: "SnapshotSortKey",
        reverse: bool = False,
    ) -> list[Snapshot]:
        """Sorts a list of Snapshot objects by a specified key.
        Snapshots with a None value for the key are placed at the end.
        String comparison is case-insensitive.

        Args:
            snapshots (list[Snapshot]): The list of Snapshots to sort.
            sort_by (SnapshotSortKey): The key to sort by, as a SnapshotSortKey enum member.
            reverse (bool): If True, sorts in descending order.

        Returns:
            list[Snapshot]: A new list containing the sorted Snapshots.
        """
        return _sorting.sort_snapshots(snapshots, sort_by, reverse)
