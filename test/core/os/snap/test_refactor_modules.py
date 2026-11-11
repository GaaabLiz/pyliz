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


def test_json_codec_round_trip_preserves_format_and_legacy_default():
    """In-memory conversion retains field ordering, indentation and OS fallback."""
    import json
    import platform

    from pylizlib.core.os.snap.storage.metadata import SnapshotJsonCodec

    snapshot = Snapshot("id", "name", "", date_created=datetime(2020, 1, 2))
    encoded = SnapshotJsonCodec.encode(snapshot)
    assert encoded.startswith('{\n    "id": "id",')
    data = json.loads(encoded)
    assert data["date_created"] == "2020-01-02T00:00:00"
    data.pop("os_created")
    decoded = SnapshotJsonCodec.decode(json.dumps(data))
    assert decoded.os_created == platform.system()
    assert decoded.date_created == snapshot.date_created


def test_serializer_keeps_subclass_text_and_converter_hooks():
    """Partial updates still use subclass I/O and conversion instead of files."""
    from pathlib import Path

    from pylizlib.core.os.snap.serializer import SnapshotSerializer

    class InMemorySerializer(SnapshotSerializer):
        """Minimal in-memory adapter exercising inherited serializer hooks."""

        result = None

        @classmethod
        def read_text(cls, path):
            """Provide an extensible object without opening a real file."""
            return '{"extension": 1}'

        @classmethod
        def write_text(cls, path, contents):
            """Capture the raw encoded object produced by partial update."""
            cls.result = contents

        @staticmethod
        def _converter(value):
            """Demonstrate the per-subclass fallback conversion hook."""
            return "custom"

    InMemorySerializer.update_field(Path("unused"), "new", object())
    assert InMemorySerializer.result == '{\n    "extension": 1,\n    "new": "custom"\n}'


@pytest.mark.parametrize("export", [False, True])
@pytest.mark.parametrize("kind,suffix", [(1, "ad"), (2, "sd")])
def test_backup_naming_and_parsing_keep_existing_grammar(export, kind, suffix):
    """Both backup types and export modes share their unchanged filename codec."""
    from pathlib import Path

    from pylizlib.core.os.snap.domain import BackupType
    from pylizlib.core.os.snap.operations.backup_names import build_backup_filename, parse_backup_filename

    name = build_backup_filename("identity", "some_prefix", BackupType(kind), "20261111_123456", export)
    assert name == f'{"" if export else "backup_"}some_prefix_identity_{suffix}_20261111_123456.zip'
    info = parse_backup_filename(Path(name))
    assert info.snapshot_id == "identity"
    assert info.prefix == "some_prefix"
    assert info.backup_type == BackupType(kind)
    assert info.is_export is export
    assert info.created_at == datetime(2026, 11, 11, 12, 34, 56)


def test_backup_parser_retains_permissive_invalid_timestamp():
    """An invalid date still permits type and ID recovery from the filename."""
    from pathlib import Path

    from pylizlib.core.os.snap.domain import BackupType
    from pylizlib.core.os.snap.operations.backup_names import parse_backup_filename

    info = parse_backup_filename(Path("backup_prefix_id_sd_20269999_999999.zip"))
    assert info.created_at is None
    assert info.backup_type is BackupType.SNAPSHOT_DIRECTORY
    assert info.snapshot_id == "id"


def test_extraction_helper_preserves_bad_zip_and_io_error_mapping(tmp_path):
    """The shared ZIP helper maps only errors in extraction, as before."""
    import zipfile
    from unittest.mock import patch

    from pylizlib.core.os.snap.storage.archives import extract_zip

    archive = tmp_path / "archive.zip"
    archive.write_bytes(b"invalid")
    with pytest.raises(ValueError, match="not a valid zip file"):
        extract_zip(archive, tmp_path / "output")
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("value", "value")
    with patch.object(zipfile.ZipFile, "extractall", side_effect=OSError("disk failed")):
        with pytest.raises(OSError, match="Failed to extract zip file.*disk failed"):
            extract_zip(archive, tmp_path / "output")


@pytest.mark.parametrize("strict", [False, True])
def test_catalogue_scanner_skips_validation_errors_in_both_modes(tmp_path, strict):
    """Strict mode propagates filesystem failures, not malformed domain metadata."""
    from unittest.mock import patch

    from pylizlib.core.os.snap.domain import SnapshotSettings
    from pylizlib.core.os.snap.storage.catalogue import read_catalogue

    (tmp_path / "entry").mkdir()
    with patch("pylizlib.core.os.snap.storage.catalogue.get_snapshot_from_path", side_effect=ValueError("invalid metadata")):
        assert read_catalogue(tmp_path, SnapshotSettings(), strict=strict) == []
    with patch("pylizlib.core.os.snap.storage.catalogue.get_snapshot_from_path", side_effect=OSError("unreadable")):
        if strict:
            with pytest.raises(OSError, match="unreadable"):
                read_catalogue(tmp_path, SnapshotSettings(), strict=True)
        else:
            assert read_catalogue(tmp_path, SnapshotSettings()) == []


@pytest.mark.parametrize("index,copied,total,expected", [(0, 1, 3, 16), (1, 0, 0, 100), (1, 1, 2, 75)])
def test_directory_progress_keeps_equal_weights_and_integer_truncation(index, copied, total, expected):
    """Percent aggregation keeps existing rounding and zero-byte behavior."""
    from pylizlib.core.os.snap.callbacks import report_directory_progress

    percentages = []
    report_directory_progress(percentages.append, index, 2, copied, total)
    assert percentages == [expected]
