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

import os
import shutil
import stat
import tempfile
import zipfile
from collections.abc import Iterable, Iterator
from pathlib import Path

from pylizlib.core.data.gen import gen_random_string
from pylizlib.core.log.pylizLogger import logger
from pylizlib.core.os.snap import diff as _diff
from pylizlib.core.os.snap import sorting as _sorting
from pylizlib.core.os.snap.copy_strategy import DirectoryCopyStrategy, SequentialFileCopyStrategy
from pylizlib.core.os.snap.domain import (
    SnapDirAssociation,
    SnapEditAction,
    Snapshot,
    SnapshotSortKey,
    validate_directory_component,
)
from pylizlib.core.os.snap.serializer import SnapshotSerializer
from pylizlib.core.os.snap.storage.tree import is_link_or_junction


class SnapshotUtils:
    @staticmethod
    def _is_link_or_junction(path: Path) -> bool:
        return is_link_or_junction(path)

    @staticmethod
    def iter_files_strict(root: Path) -> Iterator[Path]:
        """Enumerate files without suppressing scan or metadata errors.

        Directory symlinks are not traversed, matching the previous rglob
        policy. File symlinks are read; failures resolving them propagate.
        """
        if not stat.S_ISDIR(root.stat().st_mode):
            raise NotADirectoryError(f"Archive source '{root}' is not a directory.")
        pending = [root]
        while pending:
            with os.scandir(pending.pop()) as entries:
                for entry in entries:
                    mode = entry.stat(follow_symlinks=False).st_mode
                    path = Path(entry.path)
                    if stat.S_ISDIR(mode):
                        pending.append(path)
                    elif stat.S_ISREG(mode):
                        yield path
                    elif stat.S_ISLNK(mode) and stat.S_ISREG(entry.stat().st_mode):
                        yield path

    @staticmethod
    def write_verified_zip(zip_path: Path, files: Iterable[tuple[Path, Path]], message_callback=None) -> Path:
        """Publish an archive only after complete enumeration and CRC verification."""
        temporary_path = None
        try:
            zip_path.parent.mkdir(parents=True, exist_ok=True)
            # Complete enumeration before creating any archive in the source tree.
            entries = list(files)
            with tempfile.NamedTemporaryFile(dir=zip_path.parent, prefix=".backup_", suffix=".partial", delete=False) as temporary_file:
                temporary_path = Path(temporary_file.name)
            with zipfile.ZipFile(temporary_path, "w", zipfile.ZIP_DEFLATED) as archive:
                for source, archive_name in entries:
                    if message_callback:
                        message_callback(f"Archiviazione: {source.name}")
                    archive.write(source, arcname=archive_name)
            # Reopen after close: finalization can fail, and each member must
            # pass its CRC check before the normal filename becomes visible.
            with zipfile.ZipFile(temporary_path, "r") as archive:
                corrupted_member = archive.testzip()
                if corrupted_member is not None:
                    raise zipfile.BadZipFile(f"Backup validation failed for '{corrupted_member}'.")
            temporary_path.replace(zip_path)
            return zip_path
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError as e:
                    logger.warning(f"Could not remove unfinished backup '{temporary_path}': {e}")

    @staticmethod
    def cleanup_after_commit(paths: Iterable[Path], operation: str) -> None:
        """Remove transaction leftovers without rolling back committed data.

        Cleanup may have already deleted part of a backup when it fails, so
        that backup must never be used for rollback. Log each failure and
        continue cleaning the remaining paths.
        """
        for path in paths:
            try:
                if path.exists():
                    shutil.rmtree(path)
            except OSError as e:
                logger.warning(f"{operation} completed, but could not remove temporary directory '{path}': {e}")

    @staticmethod
    def assert_no_symlinks(root: Path) -> None:
        """Reject symlinks anywhere in snapshot storage before traversing it."""
        try:
            root_mode = root.lstat().st_mode
        except FileNotFoundError:
            raise
        if not stat.S_ISDIR(root_mode) or SnapshotUtils._is_link_or_junction(root):
            raise NotADirectoryError(f"Snapshot storage '{root}' is not a real directory.")

        pending = [root]
        while pending:
            current = pending.pop()
            if SnapshotUtils._is_link_or_junction(current):
                raise ValueError(f"Snapshot storage contains symbolic link '{current}'.")
            with os.scandir(current) as entries:
                for entry in entries:
                    mode = entry.stat(follow_symlinks=False).st_mode
                    entry_path = Path(entry.path)
                    if stat.S_ISLNK(mode) or SnapshotUtils._is_link_or_junction(entry_path):
                        raise ValueError(f"Snapshot storage contains symbolic link '{entry.path}'.")
                    if stat.S_ISDIR(mode):
                        pending.append(Path(entry.path))

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
        """Copy to private staging, validate it, then publish with directory renames."""
        destination_path = SnapshotUtils.get_snapshot_path(snapshot_id, catalogue_path)
        catalogue_path.mkdir(parents=True, exist_ok=True)
        catalogue_root = catalogue_path.resolve(strict=False)
        transaction_path = Path(tempfile.mkdtemp(prefix="_staging_snapshot_", dir=catalogue_root))
        staged_path = transaction_path / "snapshot"
        backup_path = transaction_path / "original"
        selected_strategy = copy_strategy or SequentialFileCopyStrategy()
        if not isinstance(selected_strategy, DirectoryCopyStrategy):
            shutil.rmtree(transaction_path)
            raise TypeError("copy_strategy must implement DirectoryCopyStrategy.")
        original_moved = False
        published = False
        preserve_transaction = False
        try:
            # Copy symlink objects into staging instead of following them. The
            # scan rejects them before any copy can become visible in storage.
            SnapshotUtils.assert_no_symlinks(source)
            selected_strategy.copy_directory(source, staged_path, message_callback=message_callback)
            SnapshotUtils.assert_no_symlinks(staged_path)
            if prepare_staging is not None:
                prepare_staging(staged_path)

            destination_path = SnapshotUtils.validate_snapshot_root(snapshot_id, catalogue_path)
            if destination_path.exists() or destination_path.is_symlink():
                if not replace_existing:
                    raise FileExistsError(f"Snapshot destination '{destination_path}' already exists.")
                destination_path.rename(backup_path)
                original_moved = True

            # Revalidate after the old entry has moved. rename() publishes the
            # staged directory itself and never writes through a destination link.
            destination_path = SnapshotUtils.validate_snapshot_root(snapshot_id, catalogue_path)
            if destination_path.exists() or destination_path.is_symlink():
                raise FileExistsError(f"Snapshot destination '{destination_path}' was recreated during publication.")
            staged_path.rename(destination_path)
            published = True
        except Exception:
            if published:
                if destination_path.is_symlink():
                    destination_path.unlink()
                elif destination_path.exists():
                    shutil.rmtree(destination_path)
            if original_moved and backup_path.exists():
                current_destination = catalogue_root / snapshot_id
                try:
                    if current_destination.is_symlink():
                        current_destination.unlink()
                    if not current_destination.exists():
                        backup_path.rename(current_destination)
                    else:
                        preserve_transaction = True
                except OSError:
                    preserve_transaction = True
                if preserve_transaction:
                    logger.error(f"{operation} rollback could not restore '{backup_path}' to '{current_destination}'.")
            raise
        finally:
            if published:
                SnapshotUtils.cleanup_after_commit([transaction_path], operation)
            elif transaction_path.exists() and not preserve_transaction:
                shutil.rmtree(transaction_path)
        return destination_path

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
        validate_directory_component(json_filename, "Snapshot JSON filename")
        path_snapshot_json = path_snapshot.joinpath(json_filename)
        if not path_snapshot_json.is_file():
            raise FileNotFoundError(f"No snapshot.json file found in {path_snapshot}.")
        return SnapshotSerializer.from_json(path_snapshot_json)

    @staticmethod
    def get_snapshot_path(folder_name: str, catalogue_path: Path) -> Path:
        """
        Constructs the full path to a snapshot's directory within the catalogue.
        Validates the folder name to prevent path traversal.

        Args:
            folder_name: The name of the snapshot's folder (usually the snapshot ID).
            catalogue_path: The base path of the snapshot catalogue.

        Returns:
            The full path to the snapshot's directory.

        Raises:
            ValueError: If the folder_name attempts path traversal or is invalid.
        """
        validate_directory_component(folder_name, "Snapshot ID")
        if not folder_name.strip():
            raise ValueError("Snapshot ID cannot be empty.")

        try:
            catalogue_resolved = catalogue_path.resolve(strict=False)
            candidate_path = catalogue_path / folder_name
            if SnapshotUtils._is_link_or_junction(candidate_path):
                raise ValueError(f"Snapshot root '{candidate_path}' cannot be a symbolic link.")
            destination_path = catalogue_resolved / folder_name
            if SnapshotUtils._is_link_or_junction(destination_path):
                raise ValueError(f"Snapshot root '{destination_path}' cannot be a symbolic link.")
            destination_resolved = destination_path.resolve(strict=False)

            # Use structural containment to distinguish the catalogue from
            # similarly prefixed sibling paths (for example, cat_evil).
            expected_path = catalogue_resolved / folder_name
            if destination_resolved == catalogue_resolved or not destination_resolved.is_relative_to(catalogue_resolved):
                raise ValueError(f"Snapshot path must be strictly contained in its catalogue. Resolved: {destination_resolved}")
            if destination_resolved != expected_path:
                raise ValueError(f"Snapshot path does not resolve to its catalogue entry: {destination_resolved}")
        except Exception as e:
            if isinstance(e, ValueError):
                raise
            raise ValueError(f"Invalid snapshot path: {e}")

        return expected_path

    @staticmethod
    def validate_snapshot_root(folder_name: str, catalogue_path: Path) -> Path:
        """Return the snapshot root, rejecting a root replaced by a symlink."""
        root = SnapshotUtils.get_snapshot_path(folder_name, catalogue_path)
        if SnapshotUtils._is_link_or_junction(root):
            raise ValueError(f"Snapshot root '{root}' cannot be a symbolic link.")
        return root

    @staticmethod
    def get_snapshot_child_path(folder_name: str, catalogue_path: Path, child_name: str) -> Path:
        """Resolve and contain a single child path beneath its snapshot root."""
        validate_directory_component(child_name)
        root = SnapshotUtils.validate_snapshot_root(folder_name, catalogue_path)
        destination = root / child_name
        if SnapshotUtils._is_link_or_junction(destination):
            raise ValueError(f"Snapshot child '{destination}' resolves through a symbolic link.")
        resolved = destination.resolve(strict=False)
        if resolved == root or not resolved.is_relative_to(root) or resolved != destination:
            raise ValueError(f"Snapshot child '{destination}' resolves outside its direct storage path.")
        return destination

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
        return SnapshotUtils.get_snapshot_child_path(folder_name, catalogue_path, json_filename)

    @staticmethod
    def get_edits_between_snapshots(old: Snapshot, new: Snapshot) -> list[SnapEditAction]:
        """
        Compares associations by stable folder_id and generates add/remove/rename actions
        required to transform the old snapshot into the new one.

        Args:
            old: The original Snapshot object.
            new: The updated Snapshot object.

        Returns:
            A list of SnapEditAction objects representing the changes.
        """
        return _diff.get_edits_between_snapshots(old, new)

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
        return _sorting.sort_snapshots(snapshots, sort_by, reverse)
