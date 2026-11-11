"""Focused contract tests for the extracted snapshot responsibilities."""

from datetime import datetime

import pytest

from pylizlib.core.os.snap.diff import get_edits_between_snapshots
from pylizlib.core.os.snap.domain import SnapDirAssociation, SnapEditType, Snapshot, SnapshotSortKey
from pylizlib.core.os.snap.sorting import sort_snapshots
from pylizlib.core.os.snap.storage.tree import is_link_or_junction


def test_diff_orders_additions_removals_then_renames():
    """Identity, not reused path names, determines the operation ordering."""
    old = Snapshot(
        "id",
        "name",
        "",
        directories=[
            SnapDirAssociation(1, "foo", "removed", 0),
            SnapDirAssociation(2, "foo", "kept", 0),
        ],
    )
    new = Snapshot(
        "id",
        "name",
        "",
        directories=[
            SnapDirAssociation(1, "foo", "kept", 0),
            SnapDirAssociation(2, "bar", "added", 0),
        ],
    )
    edits = get_edits_between_snapshots(old, new)
    assert [(e.folder_id, e.action_type) for e in edits] == [
        ("added", SnapEditType.ADD_DIR),
        ("removed", SnapEditType.REMOVE_DIR),
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


def test_tree_enumeration_reads_file_links_but_not_directory_links(tmp_path):
    """Archive traversal and strict storage validation keep distinct link policies."""
    from pylizlib.core.os.snap.storage.tree import assert_no_symlinks, iter_files_strict

    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "value").write_text("value")
    (root / "file-link").symlink_to(outside / "value")
    (root / "directory-link").symlink_to(outside, target_is_directory=True)
    assert [p.name for p in iter_files_strict(root)] == ["file-link"]
    with pytest.raises(ValueError, match="symbolic link"):
        assert_no_symlinks(root)


def test_zip_enumerates_before_creating_partial_archive(tmp_path):
    """An archive inside its input directory cannot enumerate its own partial file."""
    import zipfile

    from pylizlib.core.os.snap.storage.archives import write_verified_zip
    from pylizlib.core.os.snap.storage.tree import iter_files_strict

    (tmp_path / "value").write_text("payload")
    files = ((p, p.relative_to(tmp_path)) for p in iter_files_strict(tmp_path))
    result = write_verified_zip(tmp_path / "output.zip", files)
    with zipfile.ZipFile(result) as archive:
        assert archive.namelist() == ["value"]
        assert archive.read("value") == b"payload"


def test_failed_publication_preparation_preserves_existing_tree(tmp_path):
    """Preparation runs before moving an original snapshot aside."""
    from pylizlib.core.os.snap.storage.publication import publish_snapshot_tree

    source = tmp_path / "source"
    source.mkdir()
    (source / "new").write_text("new")
    catalogue = tmp_path / "catalogue"
    destination = catalogue / "id"
    destination.mkdir(parents=True)
    (destination / "old").write_text("old")

    def fail(_staged):
        """Reject the prepared copy before publication starts."""
        raise RuntimeError("prepare failed")

    with pytest.raises(RuntimeError, match="prepare failed"):
        publish_snapshot_tree(source, "id", catalogue, replace_existing=True, prepare_staging=fail)
    assert (destination / "old").read_text() == "old"
    assert list(catalogue.iterdir()) == [destination]


def test_extracted_paths_reject_non_component_and_contain_child(tmp_path):
    """Lexical traversal is rejected before constructing a contained child path."""
    from pylizlib.core.os.snap.storage.paths import get_snapshot_child_path, get_snapshot_path

    with pytest.raises(ValueError):
        get_snapshot_path("../escape", tmp_path)
    assert get_snapshot_child_path("id", tmp_path, "metadata.json") == tmp_path / "id" / "metadata.json"
