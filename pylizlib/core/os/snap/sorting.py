"""Snapshot ordering with case-insensitive strings and trailing missing values."""

from pylizlib.core.os.snap.domain import Snapshot, SnapshotSortKey


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
    key_attr = sort_by.value
    snaps_with_value = []
    snaps_with_none = []

    for snap in snapshots:
        if getattr(snap, key_attr) is None:
            snaps_with_none.append(snap)
        else:
            snaps_with_value.append(snap)

    def get_key(snapshot: Snapshot):
        value = getattr(snapshot, key_attr)
        if isinstance(value, str):
            return value.lower()
        return value

    sorted_snaps = sorted(snaps_with_value, key=get_key, reverse=reverse)

    return sorted_snaps + snaps_with_none
