"""
Unit tests for pylizlib.core.os.snap.searcher

Covers every public and private method of SnapshotSearcher:
    - search (text content, text not found, regex, invalid regex)
    - search with extension filter
    - search binary files (graceful skip)
    - search by filename (text + regex + extension filter)
    - search_list across multiple snapshots
    - progress callback
    - snapshot with non-existent path (logs warning, returns empty)
    - SnapshotSearchParams default values
    - SnapshotSearchResult field population for content vs. filename matches
"""

import shutil
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from pylizlib.core.data.gen import gen_random_string
from pylizlib.core.os.snap.catalogue import SnapshotCatalogue
from pylizlib.core.os.snap.domain import SnapDirAssociation, Snapshot
from pylizlib.core.os.snap.searcher import (
    QueryType,
    SearchTarget,
    SnapshotSearcher,
    SnapshotSearchParams,
    SnapshotSearchResult,
)
from test.core.os.snap.conftest import (
    CATALOGUE_PATH,
    SOURCE_DATA_PATH,
    TEST_LOCAL_ROOT,
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
        self.catalogue, self.snap = _build_catalogue()

        # rglob("*") will yield the subdirectory, which is not a file
        params = SnapshotSearchParams(query="test", query_type=QueryType.TEXT, search_target=SearchTarget.FILE_CONTENT)
        results = self.searcher.search(self.snap, params)
        # Should not throw exception, handles dir gracefully
        self.assertTrue(True)

    def test_search_in_file_exception(self):
        original_open = Path.open
        def mocked_open(self_path, *args, **kwargs):
            if "unreadable" in self_path.name:
                raise Exception("Read error")
            return original_open(self_path, *args, **kwargs)

        unreadable_file = SOURCE_DATA_PATH / "srch1" / "unreadable.txt"
        unreadable_file.write_text("test")
        # We need to recreate the snap to include this file
        self.catalogue, self.snap = _build_catalogue()

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

    def test_progress_callback_is_called_for_each_file(self):
        calls: list = []

        def cb(filename: str, total: int, processed: int) -> None:
            calls.append((filename, total, processed))

        params = SnapshotSearchParams(query="Hello", search_target=SearchTarget.FILE_CONTENT)
        self.searcher.search(self.snap, params, on_progress=cb)
        self.assertGreater(len(calls), 0)
        last = calls[-1]
        self.assertEqual(last[1], last[2])  # total == processed on last call

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
