"""Publish stored snapshot trees and clean committed transaction leftovers."""

import shutil
import tempfile
from collections.abc import Iterable
from pathlib import Path

from pylizlib.core.log.pylizLogger import logger
from pylizlib.core.os.snap.copy_strategy import DirectoryCopyStrategy, SequentialFileCopyStrategy
from pylizlib.core.os.snap.storage.paths import get_snapshot_path, validate_snapshot_root
from pylizlib.core.os.snap.storage.tree import assert_no_symlinks


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
    destination_path = get_snapshot_path(snapshot_id, catalogue_path)
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
        assert_no_symlinks(source)
        selected_strategy.copy_directory(source, staged_path, message_callback=message_callback)
        assert_no_symlinks(staged_path)
        if prepare_staging is not None:
            prepare_staging(staged_path)

        destination_path = validate_snapshot_root(snapshot_id, catalogue_path)
        if destination_path.exists() or destination_path.is_symlink():
            if not replace_existing:
                raise FileExistsError(f"Snapshot destination '{destination_path}' already exists.")
            destination_path.rename(backup_path)
            original_moved = True

        # Revalidate after the old entry has moved. rename() publishes the
        # staged directory itself and never writes through a destination link.
        destination_path = validate_snapshot_root(snapshot_id, catalogue_path)
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
            cleanup_after_commit([transaction_path], operation)
        elif transaction_path.exists() and not preserve_transaction:
            shutil.rmtree(transaction_path)
    return destination_path
