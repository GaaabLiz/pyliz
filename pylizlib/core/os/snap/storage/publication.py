"""Publish stored snapshot trees and clean committed transaction leftovers."""

import shutil
from collections.abc import Iterable
from pathlib import Path

from pylizlib.core.log.pylizLogger import logger
from pylizlib.core.os.snap.copy_strategy import DirectoryCopyStrategy, SequentialFileCopyStrategy
from pylizlib.core.os.snap.storage.paths import get_snapshot_path, validate_snapshot_root
from pylizlib.core.os.snap.storage.transactions import SnapshotTransactionJournal, recover_pending_transactions, rename_and_sync
from pylizlib.core.os.snap.storage.tree import assert_destination_outside_source, assert_no_symlinks


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
    catalogue_root = Path(catalogue_path).resolve(strict=False)
    assert_destination_outside_source(source, catalogue_root)
    destination_path = get_snapshot_path(snapshot_id, catalogue_path)
    catalogue_path.mkdir(parents=True, exist_ok=True)
    recover_pending_transactions(catalogue_root)
    had_original = destination_path.exists() or destination_path.is_symlink()
    journal = SnapshotTransactionJournal.begin(catalogue_root, "snapshot_tree", {"snapshot_id": snapshot_id, "had_original": had_original})
    transaction_path = journal.workspace
    staged_path = transaction_path / "snapshot"
    backup_path = transaction_path / "original"
    selected_strategy = copy_strategy or SequentialFileCopyStrategy()
    if not isinstance(selected_strategy, DirectoryCopyStrategy):
        journal.cleanup()
        raise TypeError("copy_strategy must implement DirectoryCopyStrategy.")
    try:
        # Copy symlink objects into staging instead of following them. The
        # scan rejects them before any copy can become visible in storage.
        assert_no_symlinks(source)
        selected_strategy.copy_directory(source, staged_path, message_callback=message_callback)
        assert_no_symlinks(staged_path)
        if prepare_staging is not None:
            prepare_staging(staged_path)

        destination_path = validate_snapshot_root(snapshot_id, catalogue_path)
        currently_exists = destination_path.exists() or destination_path.is_symlink()
        if currently_exists != had_original:
            raise FileExistsError(f"Snapshot destination '{destination_path}' changed during publication.")
        if currently_exists:
            if not replace_existing:
                raise FileExistsError(f"Snapshot destination '{destination_path}' already exists.")
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
    journal.finalize([backup_path], operation)
    try:
        (catalogue_root / ".pyliz_transactions").rmdir()
    except OSError:
        pass
    return destination_path
