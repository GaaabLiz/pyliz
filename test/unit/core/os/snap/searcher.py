"""Behavioral tests for snapshot search across content and filenames.

Covers:
    - content search (text found/not found, regex, invalid regex)
    - search with extension filter
    - search binary files (graceful skip)
    - search by filename (text + regex + extension filter)
    - search_list across multiple snapshots
    - progress callback
    - snapshot with non-existent path (logs warning, returns empty)
    - SnapshotSearchParams default values
    - SnapshotSearchResult field population for content vs. filename matches
"""

import unittest
from pathlib import Path
from unittest.mock import patch

from pylizlib.core.os.snap.catalogue import SnapshotCatalogue
from pylizlib.core.os.snap.domain import SnapDirAssociation, Snapshot
from pylizlib.core.os.snap.searcher import (
    QueryType,
    SearchTarget,
    SnapshotSearcher,
    SnapshotSearchParams,
)
from test.support.snapshot import (
    CATALOGUE_PATH,
    SOURCE_DATA_PATH,
    reset_index,
    setup_test_dirs,
    teardown_test_dirs,
)


def _build_catalogue() -> tuple[SnapshotCatalogue, Snapshot]:
    """Shared helper: creates a two-directory snapshot inside a fresh catalogue."""
    dir1 = SOURCE_DATA_PATH / "srch1"
    dir1.mkdir(exist_ok=True)
    (dir1 / "fileA.txt").write_text("Hello world\nThis is a test file.", encoding="utf-8")
    (dir1 / "fileB.txt").write_text("Another file with test content.\nHello again.", encoding="utf-8")

    dir2 = SOURCE_DATA_PATH / "srch2"
    dir2.mkdir(exist_ok=True)
    (dir2 / "fileC.log").write_text("Log file with value=12345\nSome data.", encoding="utf-8")
    (dir2 / "fileD.txt").write_text("No interesting content here.", encoding="utf-8")
    (dir2 / "binary.bin").write_bytes(b"\x80\x81\x82\xff")

    reset_index()
    snap = Snapshot(
        id="search-snap-id",
        name="SearchSnap",
        desc="",
        directories=[
            SnapDirAssociation(index=1, original_path=str(dir1), folder_id="sd1"),
            SnapDirAssociation(index=2, original_path=str(dir2), folder_id="sd2"),
        ],
        author="Test",
    )
    catalogue = SnapshotCatalogue(CATALOGUE_PATH)
    catalogue.add(snap)
    return catalogue, snap


class TestSnapshotSearcherContentSearch(unittest.TestCase):
    """Content-based search tests."""

    def setUp(self):
        setup_test_dirs()
        self.catalogue, self.snap = _build_catalogue()
        self.searcher = SnapshotSearcher(self.catalogue)

    def tearDown(self):
        teardown_test_dirs()

    def test_text_match_returns_correct_files(self):
        params = SnapshotSearchParams(
            query="Hello",
            search_target=SearchTarget.FILE_CONTENT,
            query_type=QueryType.TEXT,
        )
        results = self.searcher.search(self.snap, params)
        self.assertEqual(len(results), 2)
        names = {r.file_path.name for r in results}
        self.assertIn("fileA.txt", names)
        self.assertIn("fileB.txt", names)

    def test_text_not_found_returns_empty_list(self):
        params = SnapshotSearchParams(query="IMPOSSIBLE_STRING_xyz123")
        results = self.searcher.search(self.snap, params)
        self.assertEqual(len(results), 0)

    def test_regex_match_finds_correct_file(self):
        params = SnapshotSearchParams(
            query=r"value=\d+",
            search_target=SearchTarget.FILE_CONTENT,
            query_type=QueryType.REGEX,
        )
        results = self.searcher.search(self.snap, params)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].file_path.name, "fileC.log")

    def test_invalid_regex_returns_empty_list(self):
        params = SnapshotSearchParams(query=r"[invalid", query_type=QueryType.REGEX)
        self.assertEqual(self.searcher.search(self.snap, params), [])

    def test_extension_filter_restricts_results_to_txt(self):
        params = SnapshotSearchParams(query="file", extensions=[".txt"])
        results = self.searcher.search(self.snap, params)
        for r in results:
            self.assertEqual(r.file_path.suffix, ".txt")

    def test_extension_filter_is_case_insensitive_and_supports_compound_suffixes(self):
        source = SOURCE_DATA_PATH / "srch1"
        upper = source / "upper.TXT"
        compound = source / "archive.tar.gz"
        upper.write_text("needle", encoding="utf-8")
        compound.write_text("needle", encoding="utf-8")
        self.catalogue.update_assoc_with_installed(self.snap.id)

        upper_results = self.searcher.search(self.snap, SnapshotSearchParams(query="needle", extensions=[".txt"]))
        compound_results = self.searcher.search(self.snap, SnapshotSearchParams(query="needle", extensions=[".TAR.GZ"]))

        self.assertIn("upper.TXT", {result.file_path.name for result in upper_results})
        self.assertEqual({result.file_path.name for result in compound_results}, {"archive.tar.gz"})

    def test_cp1252_and_utf16_text_are_searchable(self):
        source = SOURCE_DATA_PATH / "srch1"
        cp1252_file = source / "western.txt"
        utf16_file = source / "unicode.txt"
        utf16_no_bom_file = source / "unicode-no-bom.txt"
        cp1252_file.write_bytes("café déjà vu".encode("cp1252"))
        utf16_file.write_text("ciao mondo", encoding="utf-16")
        utf16_no_bom_file.write_bytes("hello café".encode("utf-16-le"))
        self.catalogue.update_assoc_with_installed(self.snap.id)

        results = self.searcher.search(self.snap, SnapshotSearchParams(query="café"))
        self.assertIn("western.txt", {result.file_path.name for result in results})
        results = self.searcher.search(self.snap, SnapshotSearchParams(query="ciao mondo"))
        self.assertIn("unicode.txt", {result.file_path.name for result in results})
        results = self.searcher.search(self.snap, SnapshotSearchParams(query="hello café"))
        self.assertIn("unicode-no-bom.txt", {result.file_path.name for result in results})

    def test_late_utf8_decode_error_retries_the_file_with_cp1252(self):
        source_file = SOURCE_DATA_PATH / "srch1" / "late-western.txt"
        source_file.write_bytes(b"ASCII prefix " * 900 + "café".encode("cp1252"))
        self.catalogue.update_assoc_with_installed(self.snap.id)

        with self.assertLogs(level="WARNING") as captured:
            results = self.searcher.search(
                self.snap,
                SnapshotSearchParams(query="café", chunk_size=1024),
            )

        self.assertIn("late-western.txt", {result.file_path.name for result in results})
        self.assertTrue(any("retrying with Windows-1252" in message for message in captured.output))
        self.assertFalse(any("binary content" in message for message in captured.output))

    def test_multiline_text_match_crosses_read_chunks(self):
        source_file = SOURCE_DATA_PATH / "srch1" / "multiline.txt"
        source_file.write_text("first line\nsecond line\nthird", encoding="utf-8")
        self.catalogue.update_assoc_with_installed(self.snap.id)

        results = self.searcher.search(
            self.snap,
            SnapshotSearchParams(query="line\nsecond", chunk_size=4),
        )

        match = next(result for result in results if result.file_path.name == "multiline.txt")
        self.assertEqual(match.line_number, 1)
        self.assertEqual(match.line_content, "first line")

        regex_results = self.searcher.search(
            self.snap,
            SnapshotSearchParams(
                query=r"first line\nsecond",
                query_type=QueryType.REGEX,
                chunk_size=4,
            ),
        )
        self.assertIn("multiline.txt", {result.file_path.name for result in regex_results})

    def test_large_single_line_returns_bounded_preview_and_can_be_cancelled_mid_file(self):
        source_file = SOURCE_DATA_PATH / "srch1" / "huge.txt"
        source_file.write_text("x" * 50_000 + "needle" + "y" * 50_000, encoding="utf-8")
        self.catalogue.update_assoc_with_installed(self.snap.id)

        results = self.searcher.search(
            self.snap,
            SnapshotSearchParams(query="needle", chunk_size=256, max_line_preview_chars=80),
        )
        match = next(result for result in results if result.file_path.name == "huge.txt")
        self.assertLessEqual(len(match.line_content), 82)
        self.assertIn("needle", match.line_content)

        cancel_dir = SOURCE_DATA_PATH / "cancel-search"
        cancel_dir.mkdir(exist_ok=True)
        (cancel_dir / "cancel.txt").write_text("needle\n" + "x" * 50_000, encoding="utf-8")
        cancel_snap = Snapshot(
            id="search-cancel-snap-id",
            name="CancelSnap",
            desc="",
            directories=[SnapDirAssociation(index=1, original_path=str(cancel_dir), folder_id="cancel-folder")],
        )
        self.catalogue.add(cancel_snap)
        cancelled_calls = 0

        def cancel_during_read(filename: str, total: int, processed: int) -> bool:
            nonlocal cancelled_calls
            cancelled_calls += 1
            return cancelled_calls < 4

        results = self.searcher.search(
            cancel_snap,
            SnapshotSearchParams(query="needle", chunk_size=8, max_results=10),
            on_progress=cancel_during_read,
        )
        self.assertGreaterEqual(cancelled_calls, 4)
        self.assertLess(cancelled_calls, 10_000)
        self.assertTrue(results)

    def test_result_page_limits_and_offsets_search_results(self):
        first_page = self.searcher.search(
            self.snap,
            SnapshotSearchParams(query="Hello", max_results=1),
        )
        second_page = self.searcher.search(
            self.snap,
            SnapshotSearchParams(query="Hello", max_results=1, result_offset=1),
        )

        self.assertEqual(len(first_page), 1)
        self.assertEqual(len(second_page), 1)
        self.assertNotEqual(first_page[0].file_path, second_page[0].file_path)

    def test_max_files_bounds_the_candidate_path_list(self):
        self.catalogue.update_assoc_with_installed(self.snap.id)

        with self.assertLogs(level="WARNING") as captured:
            results = self.searcher.search(
                self.snap,
                SnapshotSearchParams(
                    query="",
                    search_target=SearchTarget.FILE_NAME,
                    max_files=1,
                    max_results=100,
                ),
            )

        self.assertEqual(len(results), 1)
        self.assertTrue(any("max_files=1" in message for message in captured.output))

    def test_regex_timeout_skips_remaining_content_without_blocking_search(self):
        source_file = SOURCE_DATA_PATH / "srch1" / "regex-heavy.txt"
        source_file.write_text("a" * 10_000 + "!", encoding="utf-8")
        self.catalogue.update_assoc_with_installed(self.snap.id)

        with self.assertLogs(level="WARNING") as captured:
            results = self.searcher.search(
                self.snap,
                SnapshotSearchParams(
                    query=r"(a|aa)+$",
                    query_type=QueryType.REGEX,
                    chunk_size=1024,
                    max_context_chars=2048,
                    regex_timeout_seconds=0.001,
                ),
            )

        self.assertEqual(results, [])
        self.assertTrue(any("timed out" in message for message in captured.output))

    def test_binary_file_is_skipped_gracefully(self):
        params = SnapshotSearchParams(query="binary")
        results = self.searcher.search(self.snap, params)
        self.assertIsInstance(results, list)  # must not raise

    def test_result_contains_line_number_and_content(self):
        params = SnapshotSearchParams(query="Hello world")
        results = self.searcher.search(self.snap, params)
        match = next(r for r in results if r.file_path.name == "fileA.txt")
        self.assertEqual(match.line_number, 1)
        self.assertEqual(match.line_content, "Hello world")
        self.assertEqual(match.snapshot_name, "SearchSnap")

    def test_search_not_dir(self):
        # Add a dummy directory association that doesn't exist
        self.snap.directories.append(SnapDirAssociation(index=99, original_path="/dummy", folder_id="dummy"))
        params = SnapshotSearchParams(query="test", query_type=QueryType.TEXT, search_target=SearchTarget.FILE_CONTENT)
        results = self.searcher.search(self.snap, params)
        self.assertNotIn("dummy", [r.file_path.name for r in results])

    def test_search_should_search_file_not_file(self):
        # Create a subdirectory inside srch1 and rebuild the snap
        sub_dir = SOURCE_DATA_PATH / "srch1" / "subdir"
        sub_dir.mkdir(exist_ok=True)
        self.catalogue.update_assoc_with_installed(self.snap.id)

        # rglob("*") will yield the subdirectory, which is not a file
        params = SnapshotSearchParams(query="test", query_type=QueryType.TEXT, search_target=SearchTarget.FILE_CONTENT)
        results = self.searcher.search(self.snap, params)
        # Directories yielded by rglob should not appear as search results.
        self.assertNotIn("subdir", {result.file_path.name for result in results})

    def test_search_in_file_exception(self):
        original_open = Path.open

        def mocked_open(self_path, *args, **kwargs):
            if "unreadable" in self_path.name:
                raise Exception("Read error")
            return original_open(self_path, *args, **kwargs)

        unreadable_file = SOURCE_DATA_PATH / "srch1" / "unreadable.txt"
        unreadable_file.write_text("test")
        # Refresh the snapshot's stored copy to include this file.
        self.catalogue.update_assoc_with_installed(self.snap.id)

        with patch.object(Path, "open", autospec=True, side_effect=mocked_open):
            params = SnapshotSearchParams(query="test", query_type=QueryType.TEXT, search_target=SearchTarget.FILE_CONTENT)
            results = self.searcher.search(self.snap, params)
            # Make sure it didn't crash and we got some results but skipped the exception one
            self.assertTrue(len(results) > 0)


class TestSnapshotSearcherFilenameSearch(unittest.TestCase):
    """Filename-based search tests."""

    def setUp(self):
        setup_test_dirs()
        self.catalogue, self.snap = _build_catalogue()
        self.searcher = SnapshotSearcher(self.catalogue)

    def tearDown(self):
        teardown_test_dirs()

    def test_filename_text_returns_single_match(self):
        params = SnapshotSearchParams(
            query="fileA",
            search_target=SearchTarget.FILE_NAME,
            query_type=QueryType.TEXT,
        )
        results = self.searcher.search(self.snap, params)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].file_path.name, "fileA.txt")

    def test_filename_match_has_no_line_number_or_content(self):
        params = SnapshotSearchParams(query="fileA", search_target=SearchTarget.FILE_NAME)
        results = self.searcher.search(self.snap, params)
        self.assertIsNone(results[0].line_number)
        self.assertIsNone(results[0].line_content)

    def test_filename_regex_returns_two_matches(self):
        params = SnapshotSearchParams(
            query=r"file[AB]\.txt$",
            search_target=SearchTarget.FILE_NAME,
            query_type=QueryType.REGEX,
        )
        results = self.searcher.search(self.snap, params)
        names = {r.file_path.name for r in results}
        self.assertEqual(names, {"fileA.txt", "fileB.txt"})

    def test_filename_extension_filter(self):
        params = SnapshotSearchParams(
            query="fileC",
            search_target=SearchTarget.FILE_NAME,
            extensions=[".log"],
        )
        self.assertEqual(len(self.searcher.search(self.snap, params)), 1)
        params2 = SnapshotSearchParams(
            query="fileC",
            search_target=SearchTarget.FILE_NAME,
            extensions=[".txt"],
        )
        self.assertEqual(len(self.searcher.search(self.snap, params2)), 0)


class TestSnapshotSearcherMultipleSnapshots(unittest.TestCase):
    """search_list across multiple snapshots and progress callback."""

    def setUp(self):
        setup_test_dirs()
        self.catalogue, self.snap = _build_catalogue()
        self.searcher = SnapshotSearcher(self.catalogue)

    def tearDown(self):
        teardown_test_dirs()

    def test_search_list_aggregates_results_across_snapshots(self):
        snap2_dir = SOURCE_DATA_PATH / "srch3"
        snap2_dir.mkdir(exist_ok=True)
        (snap2_dir / "extra.txt").write_text("Hello from snap2")
        reset_index()
        snap2 = Snapshot(
            id="search-snap2-id",
            name="SearchSnap2",
            desc="",
            directories=[SnapDirAssociation(index=1, original_path=str(snap2_dir), folder_id="sd3")],
        )
        self.catalogue.add(snap2)
        params = SnapshotSearchParams(query="Hello", search_target=SearchTarget.FILE_CONTENT)
        results = self.searcher.search_list([self.snap, snap2], params)
        snap_names = {r.snapshot_name for r in results}
        self.assertIn("SearchSnap", snap_names)
        self.assertIn("SearchSnap2", snap_names)

    def test_search_list_applies_result_page_across_snapshots(self):
        snap2_dir = SOURCE_DATA_PATH / "srch5"
        snap2_dir.mkdir(exist_ok=True)
        (snap2_dir / "extra.txt").write_text("Hello from snap2", encoding="utf-8")
        snap2 = Snapshot(
            id="search-snap-page-id",
            name="SearchSnapPage",
            desc="",
            directories=[SnapDirAssociation(index=1, original_path=str(snap2_dir), folder_id="sd5")],
        )
        self.catalogue.add(snap2)

        results = self.searcher.search_list(
            [self.snap, snap2],
            SnapshotSearchParams(query="Hello", max_results=1, result_offset=2),
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].snapshot_name, "SearchSnapPage")

    def test_search_list_reuses_loaded_snapshots_without_rereading_catalogue_metadata(self):
        from pylizlib.core.os.snap.serializer import SnapshotSerializer

        snap2_dir = SOURCE_DATA_PATH / "srch4"
        snap2_dir.mkdir(exist_ok=True)
        (snap2_dir / "value.txt").write_text("Hello again from snap2", encoding="utf-8")
        snap2 = Snapshot(
            id="search-snap3-id",
            name="SearchSnap3",
            desc="",
            directories=[SnapDirAssociation(index=1, original_path=str(snap2_dir), folder_id="sd4")],
        )
        self.catalogue.add(snap2)
        loaded_snapshots = self.catalogue.get_all()
        params = SnapshotSearchParams(query="Hello", search_target=SearchTarget.FILE_CONTENT)

        with patch.object(SnapshotSerializer, "from_json", wraps=SnapshotSerializer.from_json) as read_metadata:
            results = self.searcher.search_list(loaded_snapshots, params)

        self.assertEqual(len(results), 3)
        self.assertEqual(read_metadata.call_count, 0)

    def test_progress_callback_is_called_for_each_file(self):
        calls: list = []

        def cb(filename: str, total: int, processed: int) -> None:
            calls.append((filename, total, processed))

        params = SnapshotSearchParams(query="Hello", search_target=SearchTarget.FILE_CONTENT)
        self.searcher.search(self.snap, params, on_progress=cb)
        self.assertGreater(len(calls), 0)
        last = calls[-1]
        self.assertEqual(last[1], last[2])  # total == processed on last call

    def test_progress_callback_exceptions_propagate_during_file_reads(self):
        calls = 0

        def fail_during_read(filename: str, total: int, processed: int) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise ValueError("observer failed")

        with self.assertRaisesRegex(ValueError, "observer failed"):
            self.searcher.search(
                self.snap,
                SnapshotSearchParams(query="Hello", chunk_size=4),
                on_progress=fail_during_read,
            )

    def test_search_nonexistent_snapshot_path_returns_empty_with_warning(self):
        ghost_snap = Snapshot(
            id="ghost_id_xyz",
            name="Ghost",
            desc="",
            directories=[SnapDirAssociation(index=1, original_path="/nonexistent/path", folder_id="g1")],
        )
        params = SnapshotSearchParams(query="anything")
        with self.assertLogs(level="WARNING"):
            results = self.searcher.search(ghost_snap, params)
        self.assertEqual(results, [])


class TestSnapshotSearchParamsDefaults(unittest.TestCase):
    """SnapshotSearchParams default values."""

    def test_default_search_target_is_file_content(self):
        params = SnapshotSearchParams(query="test")
        self.assertEqual(params.search_target, SearchTarget.FILE_CONTENT)

    def test_default_query_type_is_text(self):
        params = SnapshotSearchParams(query="test")
        self.assertEqual(params.query_type, QueryType.TEXT)

    def test_default_extensions_is_empty(self):
        params = SnapshotSearchParams(query="test")
        self.assertEqual(params.extensions, [])


if __name__ == "__main__":
    unittest.main()
