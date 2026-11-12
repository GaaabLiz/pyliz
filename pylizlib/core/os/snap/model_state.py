"""Restore snapshot model state without replacing caller-owned object identities."""

from collections.abc import Iterable
from copy import deepcopy
from dataclasses import fields

from pylizlib.core.os.snap.domain import Snapshot


def restore_snapshot_model(
    snapshot: Snapshot,
    previous: Snapshot,
    *,
    association_fields: Iterable[str] = ("index", "original_path", "folder_id", "mb_size", "integrity_manifest"),
) -> None:
    """Restore a complete snapshot while reusing associations with matching IDs.

    Args:
        snapshot (Snapshot): Caller-owned model mutated in place, preserving its
            directories list and any association whose folder_id is still present.
        previous (Snapshot): Persisted state to restore; mutable values are copied.
        association_fields (Iterable[str]): Association fields to restore, in order.
            Editors retain their original explicit subset; recovery can supply the
            complete current dataclass field list. Storage names are always restored.

    Returns:
        None: After replacing snapshot fields and the contents of its directories list.

    Notes:
        This performs no persistence and is unsuitable for partial sync rollback.
        Missing associations are deep-copied; associations absent from previous are
        removed from the list. Reading previous directory_name retains its domain
        validation side effects; copied mutable values do not alias previous.
    """
    live_by_id = {association.folder_id: association for association in snapshot.directories}
    restored_directories = []
    association_fields = tuple(association_fields)

    # Reuse caller-owned associations while copying their recoverable field values.
    for old_association in previous.directories:
        association = live_by_id.get(old_association.folder_id)
        if association is None:
            association = deepcopy(old_association)
        else:
            for name in association_fields:
                setattr(association, name, deepcopy(getattr(old_association, name)))
            association._set_storage_name(old_association.directory_name)
        restored_directories.append(association)

    # Preserve the list identity as well as the outer snapshot object.
    for model_field in fields(Snapshot):
        if model_field.name != "directories":
            setattr(snapshot, model_field.name, deepcopy(getattr(previous, model_field.name)))
    snapshot.directories[:] = restored_directories
