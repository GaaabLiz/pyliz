"""Focused contract tests for the extracted snapshot responsibilities."""

from datetime import datetime

import pytest

from pylizlib.core.os.snap.diff import get_edits_between_snapshots
from pylizlib.core.os.snap.domain import SnapDirAssociation, SnapEditType, Snapshot, SnapshotSortKey
from pylizlib.core.os.snap.sorting import sort_snapshots
from pylizlib.core.os.snap.storage.tree import is_link_or_junction


def test_diff_orders_additions_and_removals_without_renaming_stable_storage_paths():
    """Association IDs determine identity while labels and indices can change."""
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
    ]
    assert old.directories[1].directory_name == new.directories[0].directory_name


def test_diff_uses_folder_id_when_path_spelling_changes_through_an_alias(tmp_path):
    """A path alias does not change the identity of an existing association."""
    source = tmp_path / "source"
    source.mkdir()
    alias = tmp_path / "source-alias"
    try:
        alias.symlink_to(source, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"symlink creation is unavailable: {error}")

    old = Snapshot("id", "name", "", directories=[SnapDirAssociation(1, str(source), "stable-id", 0)])
    new = Snapshot("id", "name", "", directories=[SnapDirAssociation(1, str(alias), "stable-id", 0)])

    assert get_edits_between_snapshots(old, new) == []


def test_diff_keeps_distinct_ids_separate_when_paths_are_aliases(tmp_path):
    """Path equivalence cannot collapse two different association identities."""
    source = tmp_path / "source"
    source.mkdir()
    alias = tmp_path / "source-alias"
    try:
        alias.symlink_to(source, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"symlink creation is unavailable: {error}")

    old = Snapshot("id", "name", "", directories=[SnapDirAssociation(1, str(source), "old-id", 0)])
    new = Snapshot("id", "name", "", directories=[SnapDirAssociation(1, str(alias), "new-id", 0)])

    edits = get_edits_between_snapshots(old, new)

    assert [(edit.folder_id, edit.action_type) for edit in edits] == [
        ("new-id", SnapEditType.ADD_DIR),
        ("old-id", SnapEditType.REMOVE_DIR),
    ]


def test_legacy_add_action_requires_id_when_multiple_associations_share_an_aliased_target(tmp_path):
    """Legacy path matching reports ambiguity, while a stable ID selects one association."""
    from pylizlib.core.os.snap.domain import SnapEditAction
    from pylizlib.core.os.snap.operations.edits import SnapshotEditPlanner

    source = tmp_path / "source"
    source.mkdir()
    alias = tmp_path / "source-alias"
    try:
        alias.symlink_to(source, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"symlink creation is unavailable: {error}")

    old = Snapshot("id", "name", "")
    requested = Snapshot(
        "id",
        "name",
        "",
        directories=[
            SnapDirAssociation(1, str(source), "source-id", 0),
            SnapDirAssociation(2, str(alias), "alias-id", 0),
        ],
    )

    with pytest.raises(ValueError, match="pass its folder_id"):
        SnapshotEditPlanner._resolve_legacy_actions(
            [SnapEditAction(SnapEditType.ADD_DIR, new_path=str(source))],
            old,
            requested,
        )

    assert SnapshotEditPlanner._resolve_legacy_actions(
        [SnapEditAction(SnapEditType.ADD_DIR, new_path=str(source), folder_id="alias-id")],
        old,
        requested,
    ) == {"alias-id": SnapEditType.ADD_DIR}


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


@pytest.mark.parametrize("link_kind", ["file", "directory", "broken", "cycle"])
def test_tree_enumeration_rejects_symbolic_links_consistently(tmp_path, link_kind):
    """Copy and archive enumerators reject links instead of following or skipping them."""
    from pylizlib.core.os.snap.storage.tree import assert_no_symlinks, iter_files_strict, iter_tree_entries_strict

    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    important = outside / "important.txt"
    important.write_text("keep me")

    link = root / "link"
    if link_kind == "file":
        target, is_directory = important, False
    elif link_kind == "directory":
        target, is_directory = outside, True
    elif link_kind == "broken":
        target, is_directory = tmp_path / "missing", False
    else:
        target, is_directory = root, True
    try:
        link.symlink_to(target, target_is_directory=is_directory)
    except OSError as error:
        pytest.skip(f"symlink creation is unavailable: {error}")

    for enumerate_tree in (iter_files_strict, iter_tree_entries_strict):
        with pytest.raises(ValueError, match="symbolic link"):
            list(enumerate_tree(root))
    with pytest.raises(ValueError, match="symbolic link"):
        assert_no_symlinks(root)
    assert important.read_text() == "keep me"


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


def test_zip_writer_clamps_pre_1980_file_timestamps(tmp_path):
    """The ZIP writer accepts old filesystem dates and clamps them to the format epoch."""
    import os
    import zipfile
    from pathlib import Path

    from pylizlib.core.os.snap.storage.archives import write_verified_zip

    source = tmp_path / "old"
    source.write_text("old data")
    os.utime(source, (0, 0))
    archive_path = write_verified_zip(tmp_path / "old.zip", [(source, Path("old"))])

    with zipfile.ZipFile(archive_path) as archive:
        assert archive.getinfo("old").date_time == (1980, 1, 1, 0, 0, 0)


@pytest.mark.parametrize(
    "member_names,limits,error",
    [
        (["one", "two"], {"max_entries": 1}, "entries"),
        (["large"], {"max_uncompressed_bytes": 3}, "configured limit"),
    ],
)
def test_zip_preflight_rejects_entry_and_expanded_size_limits(tmp_path, member_names, limits, error):
    """Resource caps reject an archive before writing any extracted member."""
    import zipfile

    from pylizlib.core.os.snap.storage.archives import extract_zip

    archive_path = tmp_path / "bounded.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        for name in member_names:
            archive.writestr(name, "payload")
    destination = tmp_path / "extracted"

    with pytest.raises(ValueError, match=error):
        extract_zip(archive_path, destination, **limits)

    assert not destination.exists() or not list(destination.iterdir())


def test_zip_preflight_checks_required_free_space_before_extraction(tmp_path):
    """The extraction volume must have room for the temp tree and publish copy."""
    import zipfile
    from types import SimpleNamespace
    from unittest.mock import patch

    from pylizlib.core.os.snap.storage.archives import extract_zip

    archive_path = tmp_path / "space.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("value", "payload")
    destination = tmp_path / "extracted"

    with patch("pylizlib.core.os.snap.storage.archives.shutil.disk_usage", return_value=SimpleNamespace(free=10)):
        with pytest.raises(OSError, match="requires 14 bytes.*only 10 bytes"):
            extract_zip(archive_path, destination, additional_space_paths=[tmp_path])

    assert not destination.exists() or not list(destination.iterdir())


def test_zip_preflight_checks_additional_publish_space_before_extraction(tmp_path):
    """Publish-space requirements are checked before any archive member is written."""
    import zipfile
    from types import SimpleNamespace
    from unittest.mock import patch

    from pylizlib.core.os.snap.storage.archives import extract_zip

    archive_path = tmp_path / "publish-space.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("value", "payload")
    destination = tmp_path / "extracted"
    destination.mkdir()

    with patch("pylizlib.core.os.snap.storage.archives.shutil.disk_usage", return_value=SimpleNamespace(free=20)):
        with pytest.raises(OSError, match="requires 107 bytes.*only 20 bytes"):
            extract_zip(archive_path, destination, additional_space_requirements=[(tmp_path, 100)])

    assert not list(destination.iterdir())


def test_zip_preflight_rejects_traversal_before_extraction(tmp_path):
    """A member path cannot escape the chosen extraction root."""
    import zipfile

    from pylizlib.core.os.snap.storage.archives import extract_zip

    archive_path = tmp_path / "traversal.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("../outside.txt", "unsafe")

    with pytest.raises(ValueError, match="escapes its extraction directory"):
        extract_zip(archive_path, tmp_path / "extracted")
    assert not (tmp_path / "outside.txt").exists()


def test_zip_tree_entries_preserve_empty_directories(tmp_path):
    """Explicit directory entries survive ZIP extraction even with no files."""
    import zipfile

    from pylizlib.core.os.snap.storage.archives import write_verified_zip
    from pylizlib.core.os.snap.storage.tree import iter_tree_entries_strict

    source = tmp_path / "source"
    nested_empty = source / "empty" / "nested"
    nested_empty.mkdir(parents=True)
    archive_path = tmp_path / "tree.zip"
    entries = ((path, path.relative_to(source)) for path in iter_tree_entries_strict(source))

    write_verified_zip(archive_path, entries)
    with zipfile.ZipFile(archive_path) as archive:
        assert archive.getinfo("empty/").is_dir()
        assert archive.getinfo("empty/nested/").is_dir()

    extracted = tmp_path / "extracted"
    with zipfile.ZipFile(archive_path) as archive:
        archive.extractall(extracted)
    assert (extracted / "empty" / "nested").is_dir()


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
    assert name == f"{'' if export else 'backup_'}some_prefix_identity_{suffix}_20261111_123456.zip"
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


@pytest.mark.parametrize("index,copied,total,expected", [(0, 1, 3, 16), (1, 0, 0, 100), (1, 1, 2, 75), (0, 4, 2, 50)])
def test_directory_progress_keeps_equal_weights_and_integer_truncation(index, copied, total, expected):
    """Percent aggregation keeps equal weights and clamps stale size estimates."""
    from pylizlib.core.os.snap.callbacks import report_directory_progress

    percentages = []
    report_directory_progress(percentages.append, index, 2, copied, total)
    assert percentages == [expected]


def test_empty_sequential_copy_reports_terminal_progress(tmp_path):
    """An empty tree still notifies observers that copying has completed."""
    from pylizlib.core.os.snap.copy_strategy import SequentialFileCopyStrategy

    source = tmp_path / "source"
    source.mkdir()
    progress = []

    SequentialFileCopyStrategy().copy_directory(source, tmp_path / "copy", lambda copied, total: progress.append((copied, total)))

    assert progress == [(0, 0)]


def test_sequential_copy_progress_finishes_against_actual_captured_size(tmp_path):
    """A stale larger pre-scan total cannot leave progress below completion."""
    from unittest.mock import patch

    from pylizlib.core.os.snap.callbacks import report_directory_progress
    from pylizlib.core.os.snap.copy_strategy import SequentialFileCopyStrategy

    source = tmp_path / "source"
    source.mkdir()
    (source / "value").write_bytes(b"new")
    byte_events = []
    percentages = []

    with patch.object(SequentialFileCopyStrategy, "_total_bytes", return_value=30):
        SequentialFileCopyStrategy().copy_directory(
            source,
            tmp_path / "copy",
            lambda copied, total: (byte_events.append((copied, total)), report_directory_progress(percentages.append, 0, 1, copied, total)),
        )

    assert byte_events == [(3, 30), (3, 3)]
    assert percentages[-1] == 100
    assert all(0 <= percentage <= 100 for percentage in percentages)


def test_reused_sequential_strategy_keeps_copy_state_per_destination(tmp_path):
    """Byte counters and captured manifests cannot leak across strategy calls."""
    from pylizlib.core.os.snap.copy_strategy import SequentialFileCopyStrategy

    source = tmp_path / "source"
    source.mkdir()
    (source / "value").write_bytes(b"12345")
    (source / "empty").mkdir()
    strategy = SequentialFileCopyStrategy()
    for name in ["first", "second"]:
        progress = []
        manifest = {}
        strategy.copy_directory(source, tmp_path / name, lambda copied, total: progress.append((copied, total)), manifest=manifest)
        assert progress == [(5, 5)]
        assert manifest["empty"] == {"type": "directory", "size": 0, "sha256": None}
        assert manifest["value"]["size"] == 5


@pytest.mark.parametrize("kind", ["sequential", "verified", "provider"])
def test_strategy_contract_rejects_wrong_manifest_without_publishing_or_mutating_output(tmp_path, kind):
    """Every shipped strategy must verify before publishing its output manifest."""
    from contextlib import contextmanager

    from pylizlib.core.os.snap.copy_strategy import ProviderSnapshotCopyStrategy, SequentialFileCopyStrategy, SourceSnapshotProvider, VerifiedFileCopyStrategy
    from pylizlib.core.os.snap.integrity import SnapshotIntegrityError

    class StableProvider(SourceSnapshotProvider):
        """Hold a test source stable for the provider's full context lifetime."""

        @contextmanager
        def create_snapshot(self, source):
            """Yield the unchanged test tree as the stable provider result."""
            yield source

    source = tmp_path / "source"
    source.mkdir()
    (source / "value").write_text("old")
    expected = {}
    SequentialFileCopyStrategy().copy_directory(source, tmp_path / "reference", manifest=expected)
    (source / "value").write_text("new")
    strategies = {
        "sequential": SequentialFileCopyStrategy(),
        "verified": VerifiedFileCopyStrategy(),
        "provider": ProviderSnapshotCopyStrategy(StableProvider()),
    }
    output = {"unchanged": {"marker": True}}
    with pytest.raises(SnapshotIntegrityError):
        strategies[kind].copy_directory(source, tmp_path / "rejected", manifest=output, expected_manifest=expected)
    assert output == {"unchanged": {"marker": True}}
    assert not (tmp_path / "rejected").exists()


def test_partial_update_resolves_writer_after_read_hook():
    """An inherited read hook may select the writer used for its subsequent update."""
    from pathlib import Path

    from pylizlib.core.os.snap.serializer import SnapshotSerializer

    calls = []

    class SwitchingSerializer(SnapshotSerializer):
        """Select an in-memory writer while reading, as the public hooks allow."""

        @classmethod
        def read_text(cls, path):
            """Install the final writer before returning the metadata object."""
            cls.write_text = staticmethod(lambda path, contents: calls.append(contents))
            return "{}"

        @classmethod
        def write_text(cls, path, contents):
            """Record incorrect early writer resolution as an observable failure."""
            raise AssertionError("writer resolved before read")

    SwitchingSerializer.update_field(Path("unused"), "field", "value")
    assert calls == ['{\n    "field": "value"\n}']


def test_full_serialization_resolves_writer_after_validation_hook():
    """Validation runs before resolving the public writer used for full saves."""
    from pathlib import Path
    from unittest.mock import patch

    from pylizlib.core.os.snap.serializer import SnapshotSerializer

    snapshot = Snapshot("id", "name", "")
    validate = snapshot.validate
    written = []

    def validate_and_select_writer():
        """Choose a writer while validating without altering the snapshot data."""
        validate()
        SnapshotSerializer.write_text = lambda path, contents: written.append(contents)

    with patch.object(SnapshotSerializer, "write_text") as original_writer:
        with patch.object(snapshot, "validate", side_effect=validate_and_select_writer):
            SnapshotSerializer.to_json(snapshot, Path("unused"))
        original_writer.assert_not_called()
    assert len(written) == 1
    assert '"id": "id"' in written[0]


def test_full_serialization_resolves_converter_after_validation_hook():
    """A validation hook can replace the fallback converter before JSON encoding."""
    import json
    from pathlib import Path
    from unittest.mock import patch

    from pylizlib.core.os.snap.serializer import SnapshotSerializer

    snapshot = Snapshot("id", "name", "")
    validate = snapshot.validate

    def select_converter():
        """Select a custom conversion after the normal domain checks."""
        validate()
        SnapshotSerializer._converter = lambda value: "selected-after-validation"

    with patch.object(SnapshotSerializer, "_converter"):
        with patch.object(snapshot, "validate", side_effect=select_converter):
            with patch.object(SnapshotSerializer, "write_text") as write:
                SnapshotSerializer.to_json(snapshot, Path("unused"))
    assert json.loads(write.call_args.args[1])["date_created"] == "selected-after-validation"
