"""Compose snapshot configurations from application fields and source paths."""

from collections.abc import Mapping, Sequence
from pathlib import Path

from pylizlib.core.data.gen import gen_random_string
from pylizlib.core.os.paths.identity import same_filesystem_entry
from pylizlib.core.os.snap.domain import SnapDirAssociation, Snapshot
from pylizlib.core.os.snap.storage.original_paths import normalize_original_path


def build_associations(
    directory_paths: Sequence[str | Path],
    folder_id_length: int,
    existing: Sequence[SnapDirAssociation] = (),
) -> list[SnapDirAssociation]:
    """Build ordered associations from paths, reusing retained association metadata.

    Args:
        directory_paths (Sequence[str | Path]): Complete ordered list of source paths.
        folder_id_length (int): Configured ID length for new associations.
        existing (Sequence[SnapDirAssociation]): Associations from an independent clone, available for reuse.

    Returns:
        list[SnapDirAssociation]: Ordered associations with zero-based indexes.

    Raises:
        ValueError: A path is invalid, duplicated or matches multiple existing associations.
    """
    if isinstance(directory_paths, str):
        raise TypeError("directory_paths must be a sequence of paths, not a single string.")
    used_ids = {association.folder_id for association in existing}
    associations: list[SnapDirAssociation] = []
    for index, path in enumerate(directory_paths):
        original_path = normalize_original_path(str(path) if isinstance(path, Path) else path)
        if any(same_filesystem_entry(original_path, association.original_path) for association in associations):
            raise ValueError(f"Duplicate snapshot directory: '{original_path}'.")
        matches = [association for association in existing if same_filesystem_entry(original_path, association.original_path)]
        if len(matches) > 1:
            raise ValueError(f"Snapshot directory '{original_path}' matches multiple existing associations.")
        if matches:
            association = matches[0]
            association.index = index
        else:
            folder_id = _new_folder_id(folder_id_length, used_ids)
            association = SnapDirAssociation(index=index, original_path=original_path, folder_id=folder_id)
            used_ids.add(folder_id)
        associations.append(association)
    return associations


def _new_folder_id(length: int, used_ids: set[str]) -> str:
    """Allocate an ID without reusing one from the original or new configuration.

    Args:
        length (int): Positive length of the generated ID.
        used_ids (set[str]): IDs reserved within this snapshot, including removed associations.

    Returns:
        str: A generated ID outside the reserved set.

    Raises:
        ValueError: The configured length is invalid.
        RuntimeError: No free ID was found within the retry limit.
    """
    if type(length) is not int or length < 1:
        raise ValueError("SnapshotSettings.folder_id_length must be a positive integer.")
    for _ in range(100):
        folder_id = gen_random_string(length)
        if folder_id not in used_ids:
            return folder_id
    raise RuntimeError("Could not allocate a unique folder ID. Increase SnapshotSettings.folder_id_length.")


def configure_snapshot(
    snapshot: Snapshot,
    folder_id_length: int,
    *,
    name: str | None,
    desc: str | None,
    tags: list[str] | None,
    directory_paths: Sequence[str | Path] | None,
    data_updates: Mapping[str, str] | None,
    data_remove: Sequence[str],
) -> Snapshot:
    """Apply a partial configuration to an independent clone of a stored snapshot.

    Args:
        snapshot (Snapshot): Current stored snapshot.
        folder_id_length (int): Configured ID length for newly associated directories.
        name (str | None): New display name, or None to preserve it.
        desc (str | None): New description, or None to preserve it.
        tags (list[str] | None): Replacement tags, or None to preserve them.
        directory_paths (Sequence[str | Path] | None): Replacement ordered paths, or None to preserve them.
        data_updates (Mapping[str, str] | None): Custom values to add or replace.
        data_remove (Sequence[str]): Custom keys to remove before applying updates.

    Returns:
        Snapshot: Validated desired model, independent of the stored model.
    """
    updated = snapshot.clone()
    if name is not None:
        updated.name = name
    if desc is not None:
        updated.desc = desc
    if tags is not None:
        updated.tags = tags.copy()
    if directory_paths is not None:
        updated.directories = build_associations(directory_paths, folder_id_length, updated.directories)
    if isinstance(data_remove, str):
        raise TypeError("data_remove must be a sequence of keys, not a single string.")
    for key in data_remove:
        updated.remove_data_item(key)
    if data_updates is not None:
        updated.data.update(data_updates)
    updated.validate()
    return updated
