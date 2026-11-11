"""Focused contract tests for the extracted snapshot responsibilities."""

from datetime import datetime

import pytest

from pylizlib.core.os.snap.diff import get_edits_between_snapshots
from pylizlib.core.os.snap.domain import SnapDirAssociation, SnapEditType, Snapshot, SnapshotSortKey
from pylizlib.core.os.snap.sorting import sort_snapshots
from pylizlib.core.os.snap.storage.tree import is_link_or_junction


def test_diff_orders_additions_removals_then_renames():
    """Identity, not reused path names, determines the operation ordering."""
    old = Snapshot("id", "name", "", directories=[
        SnapDirAssociation(1, "foo", "removed", 0),
        SnapDirAssociation(2, "foo", "kept", 0),
    ])
    new = Snapshot("id", "name", "", directories=[
        SnapDirAssociation(1, "foo", "kept", 0),
        SnapDirAssociation(2, "bar", "added", 0),
    ])
    edits = get_edits_between_snapshots(old, new)
    assert [(e.folder_id, e.action_type) for e in edits] == [
        ("added", SnapEditType.ADD_DIR), ("removed", SnapEditType.REMOVE_DIR),
        ("kept", SnapEditType.RENAME_DIR),
    ]


def test_sort_keeps_none_last_even_in_reverse_and_does_not_mutate():
    """Missing dates trail descending values without rearranging the input."""
    missing = Snapshot("none", "none", "")
    older = Snapshot("older", "older", "", date_modified=datetime(2020, 1, 1))
    newer = Snapshot("newer", "newer", "", date_modified=datetime(2021, 1, 1))
    snapshots = [missing, older, newer]
    assert sort_snapshots(snapshots, SnapshotSortKey.DATE_MODIFIED, True) == [newer, older, missing]
    assert snapshots == [missing, older, newer]


def test_entry_check_distinguishes_real_and_dangling_link(tmp_path):
    """A dangling root link remains a link even though exists() returns False."""
    assert not is_link_or_junction(tmp_path)
    link = tmp_path / "link"
    try:
        link.symlink_to(tmp_path / "missing")
    except OSError as error:
        pytest.skip(str(error))
    assert is_link_or_junction(link)
