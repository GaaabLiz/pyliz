"""Validate and recover the temporary moves made by associated-folder removal."""

import stat
from pathlib import Path

from pylizlib.core.os.paths.safety import assert_no_link_components
from pylizlib.core.os.snap.operations.destinations import validate_destructive_destinations
from pylizlib.core.os.snap.storage.context import SnapshotStorage
from pylizlib.core.os.snap.storage.transactions import SnapshotTransactionJournal, TransactionRecoveryError, rename_and_sync


def removal_displacement(journal: SnapshotTransactionJournal, destination: Path, index: int) -> Path:
    """Derive a short same-volume holding path owned by this journal.

    Args:
        journal (SnapshotTransactionJournal): Removal journal with a unique workspace name.
        destination (Path): Confirmed local directory to move.
        index (int): Entry index, unique even for siblings.

    Returns:
        Path: Generated sibling used to retain the original directory before commit.
    """
    return destination.with_name(f".pyliz_removing_{journal.workspace.name}_{index}")


def recover_association_removal(journal: SnapshotTransactionJournal, storage: SnapshotStorage) -> None:
    """Restore all displaced folders before commit, or finish cleaning them up after commit.

    Args:
        journal (SnapshotTransactionJournal): Persistent removal intent and commit decision.
        storage (SnapshotStorage): Snapshot state authorizing the recorded local paths.

    Returns:
        None: The journal is resolved, or remains for retry if cleanup fails.

    Raises:
        TransactionRecoveryError: A journal entry is invalid or a destination would be overwritten.
    """
    if journal.workspace.parent.parent != storage.path_snapshot.resolve():
        raise TransactionRecoveryError("Removal journal is outside its snapshot scope.")
    associations = {item.folder_id: Path(item.original_path).absolute() for item in storage.snapshot.directories}
    entries = journal.payload["payload"].get("entries")
    if not isinstance(entries, list) or not entries:
        raise TransactionRecoveryError("Removal journal is missing its directory entries.")

    targets = []
    for entry in entries:
        folder_id = entry.get("folder_id") if isinstance(entry, dict) else None
        if not isinstance(folder_id, str) or folder_id not in associations or str(associations[folder_id]) != entry.get("destination"):
            raise TransactionRecoveryError("Removal journal does not match the snapshot associations.")
        targets.append((folder_id, associations[folder_id]))

    destinations = validate_destructive_destinations(
        targets,
        catalogue_path=storage.path_catalogue,
        origin_os=storage.snapshot.os_created,
        operation="recover associated folder removal",
    )
    displaced = []
    for index, path in enumerate(destinations):
        holding_path = removal_displacement(journal, path, index)
        assert_no_link_components(holding_path)
        try:
            mode = holding_path.lstat().st_mode
        except FileNotFoundError:
            continue
        if not stat.S_ISDIR(mode):
            raise TransactionRecoveryError(f"Removal holding path '{holding_path}' is not a directory.")
        displaced.append((path, holding_path))

    if journal.payload["state"] in {"commit_decided", "committed"}:
        if journal.payload["state"] == "commit_decided":
            journal.set_state("committed")
        journal.finalize((holding_path for _, holding_path in displaced), "Associated folder removal")
        return

    for path, holding_path in reversed(displaced):
        if path.exists(follow_symlinks=False):
            raise TransactionRecoveryError(f"Cannot restore '{path}' because it already exists. Its original contents are at '{holding_path}'.")
        rename_and_sync(holding_path, path)
    journal.cleanup()
