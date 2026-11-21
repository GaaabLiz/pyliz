"""Snapshot ordering with case-insensitive strings and trailing missing values."""

from datetime import datetime, timedelta

from pylizlib.core.os.snap.domain import Snapshot, SnapshotSortKey


def chronological_key(value: datetime) -> timedelta:
    """Normalize an instant for ordering without modifying the persisted timestamp.

    Args:
        value (datetime): Snapshot timestamp. Naive values use local time, with UTC as the fallback for dates
            outside the platform's local conversion range.

    Returns:
        timedelta: Instant relative to datetime.min in UTC, which can be negative for early dates.
    """
    offset = value.utcoffset()
    if offset is None:
        try:
            offset = value.astimezone().utcoffset()
        except (OSError, OverflowError, ValueError):
            pass
    return value.replace(tzinfo=None) - datetime.min - (offset or timedelta())


def sort_snapshots(
    snapshots: list[Snapshot],
    sort_by: "SnapshotSortKey",
    reverse: bool = False,
) -> list[Snapshot]:
    """Sorts a list of Snapshot objects by a specified key.
    Snapshots with a None value for the key are placed at the end.
    Strings compare case-insensitively and dates compare by instant.

    Args:
        snapshots (list[Snapshot]): The list of Snapshots to sort.
        sort_by (SnapshotSortKey): The key to sort by, as a SnapshotSortKey enum member.
        reverse (bool): If True, sorts in descending order.

    Returns:
        list[Snapshot]: A new list containing the sorted Snapshots.
    """
    key_attr = sort_by.value
    snaps_with_value = []
    snaps_with_none = []

    for snap in snapshots:
        if getattr(snap, key_attr) is None:
            snaps_with_none.append(snap)
        else:
            snaps_with_value.append(snap)

    def get_key(snapshot: Snapshot):
        """Compare lowercase strings and normalized timestamps when applicable.

        Args:
            snapshot (Snapshot): Snapshot model used or mutated by this operation; association identities are retained
                where documented.

        Returns:
            object: Key comparable with other values of this snapshot field.
        """
        value = getattr(snapshot, key_attr)
        if isinstance(value, str):
            return value.lower()
        if isinstance(value, datetime):
            return chronological_key(value)
        return value

    sorted_snaps = sorted(snaps_with_value, key=get_key, reverse=reverse)

    return sorted_snaps + snaps_with_none
