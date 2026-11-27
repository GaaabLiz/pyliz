"""Back up and transactionally remove confirmed live snapshot associations."""

import stat
from collections.abc import Collection
from pathlib import Path

from pylizlib.core.os.paths.safety import assert_no_link_components
from pylizlib.core.os.snap.callbacks import MessageCallback
from pylizlib.core.os.snap.domain import SnapDirAssociation
from pylizlib.core.os.snap.operations.archives import SnapshotArchiveService
from pylizlib.core.os.snap.operations.backup.creation import verify_displaced_sources
from pylizlib.core.os.snap.operations.destinations import validate_destructive_destinations
from pylizlib.core.os.snap.storage.context import SnapshotStorage
from pylizlib.core.os.snap.storage.recovery.removal import removal_displacement
from pylizlib.core.os.snap.storage.transactions import SnapshotTransactionJournal, rename_and_sync


def existing_associations(storage: SnapshotStorage) -> list[tuple[SnapDirAssociation, Path]]:
    """Select live directories and validate their paths before confirmation or removal.

    Args:
        storage (SnapshotStorage): Fresh snapshot state, catalogue and backup settings.

    Returns:
        list[tuple[SnapDirAssociation, Path]]: Associations paired with present local directories.

    Raises:
        NotADirectoryError: An associated entry exists and is not a directory.
        ValueError: A selected directory is unsafe for removal.
    """
    targets = []
    for association in storage.snapshot.directories:
        path = Path(association.original_path).absolute()
        try:
            mode = path.lstat().st_mode
        except FileNotFoundError:
            continue
        if not stat.S_ISDIR(mode):
            raise NotADirectoryError(f"The associated path '{path}' must point to a local folder.")
        targets.append((association, path))

    if targets:
        validate_destructive_destinations(
            ((association.folder_id, path) for association, path in targets),
            catalogue_path=storage.path_catalogue,
            origin_os=storage.snapshot.os_created,
            operation="delete associated folders",
            backup_path=storage.settings.backup_path,
        )
    return targets


def remove_confirmed_associations(
    storage: SnapshotStorage,
    expected_paths: Collection[Path],
    *,
    verify_backup: bool = False,
    message_callback: MessageCallback | None = None,
) -> Path | None:
    """Archive and remove the exact confirmed association paths under the catalogue lock.

    Args:
        storage (SnapshotStorage): Fresh snapshot state, catalogue and backup settings.
        expected_paths (Collection[Path]): Exact local paths shown for confirmation.
        verify_backup (bool): Compare the displaced trees with the ZIP before committing.
        message_callback (MessageCallback | None): Optional callback for backup progress messages.

    Returns:
        Path | None: Published archive, or None when no directories were confirmed or remain.

    Raises:
        SourceChangedError: Verification found a discrepancy and the displaced directories were restored.
        ValueError: Confirmed paths changed, backup storage is unset, or a destination is unsafe.
    """
    targets = existing_associations(storage)
    if {path for _, path in targets} != set(expected_paths):
        raise ValueError("The associated folders changed. Review the list and try again.")
    if not targets:
        return None

    backup_path = storage.settings.backup_path
    if backup_path is None:
        raise ValueError("Set a backup folder before deleting associated folders.")
    archive = SnapshotArchiveService(storage).create_backup_for_associations(
        backup_path, "beforeRemove", [association for association, _ in targets], message_callback,
    )

    entries = [{"folder_id": association.folder_id, "destination": str(path)} for association, path in targets]
    journal = SnapshotTransactionJournal.begin(storage.path_snapshot, "remove_associations", {"entries": entries})
    displaced = {}
    try:
        for index, (association, path) in enumerate(targets):
            holding_path = removal_displacement(journal, path, index)
            assert_no_link_components(path)
            if not stat.S_ISDIR(path.lstat().st_mode):
                raise NotADirectoryError(path)
            if holding_path.exists(follow_symlinks=False):
                raise FileExistsError(holding_path)
            rename_and_sync(path, holding_path)
            displaced[association.directory_name] = holding_path

        if verify_backup:
            verify_displaced_sources(archive, displaced, subject="Associated folder")
    except Exception:
        journal.decide_rollback(storage)
        raise

    journal.set_state("commit_decided")
    journal.recover(storage)
    return archive
