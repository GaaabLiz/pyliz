"""Restore snapshot model state without replacing caller-owned object identities."""

from collections.abc import Iterable
from copy import deepcopy
from dataclasses import dataclass, fields
from datetime import datetime

from pylizlib.core.os.snap.domain import Snapshot
from pylizlib.core.os.snap.integrity import IntegrityManifest


@dataclass(frozen=True)
class CapturedContentState:
    """Retain the exact manifest/size references and interval of a prior acquisition.

    Attributes:
        association_metadata (dict[str, tuple[IntegrityManifest | None, float | None]]):
            Original manifest references and MiB sizes by stable association ID.
        capture_times (tuple[datetime | None, datetime | None]): Previous start and
            completion instants. No timezone conversion or cloning is performed.
    """

    association_metadata: dict[str, tuple[IntegrityManifest | None, float | None]]
    capture_times: tuple[datetime | None, datetime | None]

    @classmethod
    def capture(cls, snapshot: Snapshot) -> "CapturedContentState":
        """Remember fields affected by content acquisition without scanning sources.

        Args:
            snapshot (Snapshot): Live model whose acquisition is about to begin.

        Returns:
            CapturedContentState: Original references and values; in-place mutations
            of an original manifest remain visible, matching the previous rollback.
        """
        metadata = {association.folder_id: (association.integrity_manifest, association.mb_size) for association in snapshot.directories}
        times = (snapshot.capture_started_at, snapshot.capture_completed_at)
        return cls(metadata, times)

    def restore_associations(self, snapshot: Snapshot) -> None:
        """Restore only manifests and sizes, keeping association object identity.

        Args:
            snapshot (Snapshot): Model with the same association IDs as at capture.

        Returns:
            None: Original manifest references and size values are reassigned.

        Raises:
            KeyError: If the association set changed during the operation.
        """
        for association in snapshot.directories:
            association.integrity_manifest, association.mb_size = self.association_metadata[association.folder_id]

    def restore_capture_interval(self, snapshot: Snapshot) -> None:
        """Restore only the acquisition interval, without touching modification dates.

        Args:
            snapshot (Snapshot): Live model whose prior interval should be restored.

        Returns:
            None: Start and completion are reassigned in their original order.
        """
        snapshot.capture_started_at, snapshot.capture_completed_at = self.capture_times


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
