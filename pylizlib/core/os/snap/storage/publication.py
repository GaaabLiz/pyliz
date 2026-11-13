"""Publish stored snapshot trees and clean committed transaction leftovers."""

import shutil
from collections.abc import Callable, Iterable
from pathlib import Path

from pylizlib.core.log.pylizLogger import logger
from pylizlib.core.os.snap.copy_strategy import DirectoryCopyStrategy, SequentialFileCopyStrategy
from pylizlib.core.os.snap.domain import Snapshot, validate_directory_component
from pylizlib.core.os.snap.integrity import assert_manifest_matches, build_integrity_manifest
from pylizlib.core.os.snap.serializer import SnapshotSerializer
from pylizlib.core.os.snap.storage.paths import assert_no_transaction_storage, get_snapshot_path, validate_snapshot_root
from pylizlib.core.os.snap.storage.transactions import SnapshotTransactionJournal, recover_pending_transactions, rename_and_sync
from pylizlib.core.os.snap.storage.tree import assert_destination_outside_source, assert_no_symlinks


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
    for path in paths:
        try:
            if path.exists():
                shutil.rmtree(path)
        except OSError as e:
            logger.warning(f"{operation} completed, but could not remove temporary directory '{path}': {e}")


def validate_staged_snapshot_tree(
    staged_path: Path,
    snapshot_id: str,
    json_filename: str,
    metadata_reader: Callable[[Path], Snapshot] | None = None,
) -> Snapshot:
    """Validate staged identity, completeness and all available content manifests.

    Args:
        staged_path (Path): Completed private snapshot tree to inspect before publication.
        snapshot_id (str): Snapshot ID expected in metadata and used for the destination directory.
        json_filename (str): Single metadata filename below the snapshot root, normally snapshot.json.
        metadata_reader (Callable[[Path], Snapshot] | None): Optional protected JSON-to-Snapshot hook; None uses
            SnapshotSerializer.from_json.

    Returns:
        Snapshot: Decoded snapshot after checking ID, real association directories and available content manifests.
            Legacy associations without manifests retain unknown integrity and remain subject to install policy.

    Raises:
        FileNotFoundError: A required source, stored association or metadata entry is absent.
        ValueError: A value, path, resource limit or metadata field violates the validation rules described above.
        SnapshotIntegrityError: An observed association differs in paths, types, sizes or hashes from its manifest.
    """
    staged_path = Path(staged_path)
    assert_no_symlinks(staged_path)
    assert_no_transaction_storage(staged_path)
    json_path = staged_path / validate_directory_component(json_filename, "Snapshot JSON filename")
    if not json_path.is_file():
        raise FileNotFoundError(f"Staged snapshot metadata '{json_path}' is missing.")
    snapshot = (metadata_reader or SnapshotSerializer.from_json)(json_path)
    if snapshot.id != snapshot_id:
        raise ValueError(f"Staged snapshot metadata ID '{snapshot.id}' does not match destination ID '{snapshot_id}'.")
    for association in snapshot.directories:
        association_path = staged_path / association.directory_name
        if not association_path.is_dir():
            raise FileNotFoundError(f"Staged association directory '{association_path}' is missing.")
        if association.integrity_manifest is not None:
            assert_manifest_matches(association.integrity_manifest, build_integrity_manifest(association_path))
    return snapshot


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

    Raises:
        TypeError: An argument or mutable model field has a type rejected by this contract.
        FileExistsError: A destination or generated staging name already exists or changes before publication.
        FileNotFoundError: A required source, stored association or metadata entry is absent.
    """

    # Incoming trees cannot introduce instructions into locally trusted recovery storage.
    assert_no_transaction_storage(Path(source))

    # Validate containment and recover older work before allocating a new journal.
    catalogue_root = Path(catalogue_path).resolve(strict=False)
    assert_destination_outside_source(source, catalogue_root)
    destination_path = get_snapshot_path(snapshot_id, catalogue_path)
    catalogue_path.mkdir(parents=True, exist_ok=True)
    recover_pending_transactions(catalogue_root)
    had_original = destination_path.exists() or destination_path.is_symlink()

    # Record intent before copying or moving any visible destination.
    journal = SnapshotTransactionJournal.begin(catalogue_root, "snapshot_tree", {"snapshot_id": snapshot_id, "had_original": had_original})
    transaction_path = journal.workspace
    staged_path = transaction_path / "snapshot"
    backup_path = transaction_path / "original"
    selected_strategy = copy_strategy or SequentialFileCopyStrategy()
    if not isinstance(selected_strategy, DirectoryCopyStrategy):
        journal.cleanup()
        raise TypeError("copy_strategy must implement DirectoryCopyStrategy.")

    # Reject source links, then recheck the completed private copy before publication.
    try:
        assert_no_symlinks(source)
        selected_strategy.copy_directory(source, staged_path, message_callback=message_callback)
        assert_no_symlinks(staged_path)
        if prepare_staging is not None:
            prepare_staging(staged_path)
        assert_no_symlinks(staged_path)
        assert_no_transaction_storage(staged_path)

        # Recheck the target after staging; concurrent presence changes abort publication.
        destination_path = validate_snapshot_root(snapshot_id, catalogue_path)
        currently_exists = destination_path.exists() or destination_path.is_symlink()
        if currently_exists != had_original:
            raise FileExistsError(f"Snapshot destination '{destination_path}' changed during publication.")
        if currently_exists:
            if not replace_existing:
                raise FileExistsError(f"Snapshot destination '{destination_path}' already exists.")

        # Persist commit intent before moving the old root aside.
        journal.set_state("commit_decided")
        if currently_exists:
            rename_and_sync(destination_path, backup_path)

        # Revalidate after the old entry has moved. rename() publishes the
        # staged directory itself and never writes through a destination link.
        destination_path = validate_snapshot_root(snapshot_id, catalogue_path)
        if destination_path.exists() or destination_path.is_symlink():
            raise FileExistsError(f"Snapshot destination '{destination_path}' was recreated during publication.")
        rename_and_sync(staged_path, destination_path)
        if not destination_path.is_dir():
            raise FileNotFoundError(f"Published snapshot '{destination_path}' is not visible after its rename.")
        journal.set_state("committed")
    except Exception as error:
        try:
            journal.decide_rollback()
        except Exception as rollback_error:
            logger.error(f"{operation} rollback is incomplete; journal retained at '{journal.path}': {rollback_error}")
            error.add_note(f"Persistent recovery journal retained at '{journal.path}'.")
        raise

    # Committed cleanup never changes the decision to keep the published tree.
    journal.finalize([backup_path], operation)
    try:
        (catalogue_root / ".pyliz_transactions").rmdir()
    except OSError:
        pass
    return destination_path
