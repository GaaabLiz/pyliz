import os
import shutil
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from pylizlib.media.lizmedia import LizMedia, LizMediaSearchResult, MediaStatus
from pylizlib.media.script.organizer.domain import OrganizerOptions
from pylizlib.media.script.organizer.media_org import MediaOrganizer

TEST_DATETIME = datetime(2023, 10, 27, 10, 30, 0)
TEST_DATETIME_EXIF = datetime(2022, 5, 15, 8, 0, 0)


class TestMediaOrganizer(unittest.TestCase):
    """Test suite for the MediaOrganizer class."""

    def setUp(self):
        """Set up temporary directories and dummy files for tests."""
        self.test_dir = Path(tempfile.mkdtemp(prefix="pyliz_test_"))
        self.source_dir = self.test_dir / "source"
        self.target_dir = self.test_dir / "target"
        self.source_dir.mkdir()
        self.target_dir.mkdir()

    def tearDown(self):
        """Remove temporary directories after tests."""
        shutil.rmtree(self.test_dir)

    def _create_dummy_file(self, filename, content="dummy_content", dt=None, subdir=""):
        """Creates a dummy file with specified content and modification time."""
        dir_path = self.source_dir / subdir
        dir_path.mkdir(exist_ok=True, parents=True)
        filepath = dir_path / filename
        filepath.write_text(content)
        if dt:
            timestamp = dt.timestamp()
            os.utime(filepath, (timestamp, timestamp))
        return filepath

    def _create_mock_search_result(self, file_path, creation_date, has_exif=False, sidecars=None, has_lizmedia=True):
        """Helper to create a mock LizMediaSearchResult."""
        media = MagicMock(spec=LizMedia)
        media.path = Path(file_path)
        media.file_name = Path(file_path).name
        media.year = creation_date.year
        media.month = creation_date.month
        media.day = creation_date.day
        media.creation_time = creation_date
        media.is_image = has_exif
        media.creation_date_from_exif_or_file_or_sidecar = creation_date if has_exif else creation_date
        media.attached_sidecar_files = [Path(p) for p in sidecars] if sidecars else []

        search_result = MagicMock(spec=LizMediaSearchResult)
        search_result.media = media
        search_result.has_lizmedia.return_value = has_lizmedia
        search_result.has_sidecars.return_value = bool(sidecars)

        return search_result

    # --- Core Functionality Tests ---

    def test_organize_simple_move(self):
        """Test a basic move operation."""
        file = self._create_dummy_file("test.jpg", dt=TEST_DATETIME)
        search_results = [self._create_mock_search_result(file, TEST_DATETIME)]
        options = OrganizerOptions(copy=False, dry_run=False)

        organizer = MediaOrganizer(search_results, str(self.target_dir), options)
        organizer.organize()

        expected_path = self.target_dir / "2023" / "10" / "test.jpg"
        self.assertTrue(expected_path.exists())
        self.assertFalse(file.exists())
        results = organizer.get_results()
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].success)
        self.assertEqual(results[0].destination_path, str(expected_path))

    def test_organize_simple_copy(self):
        """Test a basic copy operation."""
        file = self._create_dummy_file("test_copy.jpg", dt=TEST_DATETIME)
        search_results = [self._create_mock_search_result(file, TEST_DATETIME)]
        options = OrganizerOptions(copy=True, dry_run=False)

        organizer = MediaOrganizer(search_results, str(self.target_dir), options)
        organizer.organize()

        expected_path = self.target_dir / "2023" / "10" / "test_copy.jpg"
        self.assertTrue(expected_path.exists())
        self.assertTrue(file.exists())  # Source file should still exist

    def test_dry_run_no_changes(self):
        """Test that dry_run performs no actual file operations."""
        file = self._create_dummy_file("test_dryrun.jpg", dt=TEST_DATETIME)
        search_results = [self._create_mock_search_result(file, TEST_DATETIME)]
        options = OrganizerOptions(copy=False, dry_run=True)

        organizer = MediaOrganizer(search_results, str(self.target_dir), options)
        organizer.organize()

        self.assertFalse(any(self.target_dir.iterdir())) # Target should be empty
        self.assertTrue(file.exists()) # Source should be untouched

    def test_organize_with_empty_search_results(self):
        """Test that organizing an empty list results in no operations."""
        organizer = MediaOrganizer([], str(self.target_dir), OrganizerOptions())
        organizer.organize()
        self.assertEqual(len(organizer.get_results()), 0)
        self.assertFalse(any(self.target_dir.iterdir()))

    # --- Path and Date Logic Tests ---

    def test_path_building_options(self):
        """Test different path building options like 'daily' and 'no_year'."""
        # Daily
        file_daily = self._create_dummy_file("daily.jpg", dt=TEST_DATETIME)
        search_daily = [self._create_mock_search_result(file_daily, TEST_DATETIME)]
        options_daily = OrganizerOptions(daily=True)
        organizer_daily = MediaOrganizer(search_daily, str(self.target_dir), options_daily)
        organizer_daily.organize()
        expected_path_daily = self.target_dir / "2023" / "10" / "27" / "daily.jpg"
        self.assertTrue(expected_path_daily.exists())

        # No Year
        file_noyear = self._create_dummy_file("noyear.jpg", dt=TEST_DATETIME)
        search_noyear = [self._create_mock_search_result(file_noyear, TEST_DATETIME)]
        options_noyear = OrganizerOptions(no_year=True)
        organizer_noyear = MediaOrganizer(search_noyear, str(self.target_dir), options_noyear)
        organizer_noyear.organize()
        expected_path_noyear = self.target_dir / "2023-10" / "noyear.jpg"
        self.assertTrue(expected_path_noyear.exists())
        
    def test_date_source_exif(self):
        """Test that EXIF date is preferred when option is set."""
        file = self._create_dummy_file("exif.jpg", dt=TEST_DATETIME)
        search_results = [self._create_mock_search_result(file, TEST_DATETIME_EXIF, has_exif=True)]
        options = OrganizerOptions(exif=True)

        organizer = MediaOrganizer(search_results, str(self.target_dir), options)
        organizer.organize()

        expected_path = self.target_dir / str(TEST_DATETIME_EXIF.year) / f"{TEST_DATETIME_EXIF.month:02d}" / "exif.jpg"
        self.assertTrue(expected_path.exists())

    # --- Duplicate and Conflict Handling Tests ---

    def test_duplicate_handling_skip(self):
        """Test skipping a duplicate file."""
        file_content = "identical content"
        source_file = self._create_dummy_file("duplicate.jpg", content=file_content, dt=TEST_DATETIME)
        
        target_path = self.target_dir / "2023" / "10"
        target_path.mkdir(parents=True)
        (target_path / "duplicate.jpg").write_text(file_content)

        search_results = [self._create_mock_search_result(source_file, TEST_DATETIME)]
        options = OrganizerOptions(delete_duplicates=False)
        organizer = MediaOrganizer(search_results, str(self.target_dir), options)
        organizer.organize()

        self.assertTrue(source_file.exists())
        results = organizer.get_results()
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].success)
        self.assertEqual(results[0].reason, "Duplicate skipped")

    def test_duplicate_handling_delete(self):
        """Test deleting a duplicate file."""
        file_content = "identical content to delete"
        source_file = self._create_dummy_file("delete_me.jpg", content=file_content, dt=TEST_DATETIME)

        target_path = self.target_dir / "2023" / "10"
        target_path.mkdir(parents=True)
        (target_path / "delete_me.jpg").write_text(file_content)

        search_results = [self._create_mock_search_result(source_file, TEST_DATETIME)]
        options = OrganizerOptions(delete_duplicates=True)
        organizer = MediaOrganizer(search_results, str(self.target_dir), options)
        organizer.organize()

        self.assertFalse(source_file.exists())
        results = organizer.get_results()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].reason, "Duplicate deleted")

    def test_conflict_handling(self):
        """Test handling a file conflict (same name, different content)."""
        source_file = self._create_dummy_file("conflict.jpg", content="source content", dt=TEST_DATETIME)

        target_path = self.target_dir / "2023" / "10"
        target_path.mkdir(parents=True)
        (target_path / "conflict.jpg").write_text("target content")

        search_results = [self._create_mock_search_result(source_file, TEST_DATETIME)]
        organizer = MediaOrganizer(search_results, str(self.target_dir), OrganizerOptions())
        organizer.organize()

        self.assertTrue(source_file.exists())
        results = organizer.get_results()
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].success)
        self.assertEqual(results[0].reason, "File conflict: target exists but content differs")

    @patch('pylizlib.media.script.organizer.media_org.os.path.getsize', return_value=200 * 1024 * 1024)
    def test_duplicate_check_with_large_file(self, mock_getsize):
        """Test duplicate check when files are too large for hashing."""
        source_file = self._create_dummy_file("large.jpg", content="source", dt=TEST_DATETIME)
        target_path = self.target_dir / "2023" / "10"
        target_path.mkdir(parents=True)
        (target_path / "large.jpg").write_text("target") # Different content

        search_results = [self._create_mock_search_result(source_file, TEST_DATETIME)]
        organizer = MediaOrganizer(search_results, str(self.target_dir), OrganizerOptions())
        # Since hash becomes "LARGE_FILE" for both, they are considered duplicates
        organizer.organize()

        results = organizer.get_results()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].reason, "Duplicate skipped")
        self.assertTrue(source_file.exists())

    # --- Sidecar Handling Tests ---

    def test_sidecar_handling_move(self):
        """Test that sidecar files are moved with the main file."""
        main_file = self._create_dummy_file("media.jpg", dt=TEST_DATETIME)
        sidecar_xmp = self._create_dummy_file("media.xmp", dt=TEST_DATETIME)
        sidecar_aae = self._create_dummy_file("media.aae", dt=TEST_DATETIME)

        search_results = [self._create_mock_search_result(main_file, TEST_DATETIME, sidecars=[sidecar_xmp, sidecar_aae])]
        organizer = MediaOrganizer(search_results, str(self.target_dir), OrganizerOptions())
        organizer.organize()

        expected_dir = self.target_dir / "2023" / "10"
        self.assertTrue((expected_dir / "media.jpg").exists())
        self.assertTrue((expected_dir / "media.xmp").exists())
        self.assertTrue((expected_dir / "media.aae").exists())
        self.assertFalse(main_file.exists())
        self.assertFalse(sidecar_xmp.exists())

    def test_sidecar_handling_with_skipped_duplicate_main_file(self):
        """Test that sidecars are moved even if the main file is a skipped duplicate."""
        main_file = self._create_dummy_file("dup_main.jpg", content="content", dt=TEST_DATETIME)
        sidecar_file = self._create_dummy_file("dup_main.xmp", content="sidecar", dt=TEST_DATETIME)
        
        target_path = self.target_dir / "2023" / "10"
        target_path.mkdir(parents=True)
        (target_path / "dup_main.jpg").write_text("content")

        search_results = [self._create_mock_search_result(main_file, TEST_DATETIME, sidecars=[sidecar_file])]
        organizer = MediaOrganizer(search_results, str(self.target_dir), OrganizerOptions(copy=True))
        organizer.organize()

        self.assertTrue((target_path / "dup_main.xmp").exists())
        self.assertTrue(sidecar_file.exists())
        results = organizer.get_results()
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].reason, "Duplicate skipped")
        self.assertTrue(results[1].success)
        self.assertEqual(results[1].source_file.name, "dup_main.xmp")

    def test_sidecar_skipped_if_already_exists(self):
        """Test that a sidecar is skipped if it already exists at the target."""
        main_file = self._create_dummy_file("with_sidecar.jpg", dt=TEST_DATETIME)
        sidecar_file = self._create_dummy_file("with_sidecar.xmp", dt=TEST_DATETIME)

        target_path = self.target_dir / "2023" / "10"
        target_path.mkdir(parents=True)
        (target_path / "with_sidecar.xmp").write_text("existing sidecar")

        search_results = [self._create_mock_search_result(main_file, TEST_DATETIME, sidecars=[sidecar_file])]
        organizer = MediaOrganizer(search_results, str(self.target_dir), OrganizerOptions(copy=True))
        organizer.organize()

        results = organizer.get_results()
        main_result = next(r for r in results if r.source_file.name == "with_sidecar.jpg")
        sidecar_result = next(r for r in results if r.source_file.name == "with_sidecar.xmp")

        self.assertTrue(main_result.success)
        self.assertFalse(sidecar_result.success)
        self.assertEqual(sidecar_result.reason, "Sidecar exists/Duplicate skipped")
        self.assertEqual((target_path / "with_sidecar.xmp").read_text(), "existing sidecar")

    def test_sidecar_skipped_when_main_fails(self):
        """Test that sidecars are not processed if the main file fails for a critical reason."""
        main_file = self._create_dummy_file("fail.jpg", content="source", dt=TEST_DATETIME)
        sidecar_file = self._create_dummy_file("fail.xmp", dt=TEST_DATETIME)

        target_path = self.target_dir / "2023" / "10"
        target_path.mkdir(parents=True)
        (target_path / "fail.jpg").write_text("target") # Create a conflict

        search_results = [self._create_mock_search_result(main_file, TEST_DATETIME, sidecars=[sidecar_file])]
        organizer = MediaOrganizer(search_results, str(self.target_dir), OrganizerOptions())
        organizer.organize()

        self.assertEqual(len(organizer.get_results()), 1) # Only one result for the failed main file
        self.assertEqual(organizer.get_results()[0].reason, "File conflict: target exists but content differs")
        self.assertTrue(sidecar_file.exists()) # Sidecar should be untouched
        self.assertFalse((target_path / "fail.xmp").exists()) # And not moved

    # --- Error Handling and Edge Case Tests ---

    def test_error_no_lizmedia(self):
        """Test that items without a LizMedia object are skipped."""
        file = self._create_dummy_file("no_media.txt")
        search_result = self._create_mock_search_result(file, TEST_DATETIME, has_lizmedia=False)
        organizer = MediaOrganizer([search_result], str(self.target_dir), OrganizerOptions())
        organizer.organize()
        self.assertEqual(len(organizer.get_results()), 0)

    @patch('pylizlib.media.script.organizer.media_org.MediaOrganizer._sanitize_path', side_effect=ValueError("Path contains invalid traversal components"))
    def test_process_item_handles_sanitize_error(self, mock_sanitize):
        """Test that _process_single_item correctly handles a ValueError from _sanitize_path."""
        file = self._create_dummy_file("anyfile.jpg", dt=TEST_DATETIME)
        search_results = [self._create_mock_search_result(file, TEST_DATETIME)]
        organizer = MediaOrganizer(search_results, str(self.target_dir), OrganizerOptions())
        organizer.organize()
        results = organizer.get_results()
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].success)
        self.assertEqual(results[0].reason, "Path contains invalid traversal components")

    def test_unit_sanitize_path(self):
        """Unit test the _sanitize_path method directly."""
        organizer = MediaOrganizer([], "", OrganizerOptions())
        # The regex was fixed, so this should now work as expected on Windows
        with self.assertRaisesRegex(ValueError, "Path contains invalid traversal components"):
            organizer._sanitize_path("source/../file.jpg")
        with self.assertRaisesRegex(ValueError, "Path contains invalid traversal components"):
            organizer._sanitize_path("../file.jpg")
        # Test valid path
        valid_path = str(self.source_dir / "file.jpg")
        self.assertEqual(organizer._sanitize_path(valid_path), valid_path)

    @patch('pylizlib.media.script.organizer.media_org.os.access', return_value=False)
    def test_error_no_write_permission(self, mock_access):
        """Test failure when write permission is denied for the target folder."""
        file = self._create_dummy_file("permission_denied.jpg", dt=TEST_DATETIME)
        search_results = [self._create_mock_search_result(file, TEST_DATETIME)]
        organizer = MediaOrganizer(search_results, str(self.target_dir), OrganizerOptions())
        organizer.organize()
        
        results = organizer.get_results()
        self.assertFalse(results[0].success)
        self.assertIn("write permission denied", results[0].reason.lower())
        self.assertTrue(file.exists())

    @patch('pylizlib.media.script.organizer.media_org.tqdm')
    def test_progress_bar_toggle(self, mock_tqdm):
        """Test that the progress bar is toggled correctly."""
        file = self._create_dummy_file("progress.jpg", dt=TEST_DATETIME)
        search_results = [self._create_mock_search_result(file, TEST_DATETIME)]

        # With progress bar
        options_progress = OrganizerOptions(no_progress=False)
        organizer_progress = MediaOrganizer(search_results, str(self.target_dir), options_progress)
        organizer_progress.organize()
        mock_tqdm.assert_called_once()
        
        mock_tqdm.reset_mock()
        
        # Without progress bar
        self.setUp() # Reset dirs
        file = self._create_dummy_file("progress.jpg", dt=TEST_DATETIME)
        search_results = [self._create_mock_search_result(file, TEST_DATETIME)]
        options_no_progress = OrganizerOptions(no_progress=True)
        organizer_no_progress = MediaOrganizer(search_results, str(self.target_dir), options_no_progress)
        organizer_no_progress.organize()
        mock_tqdm.assert_not_called()

    # --- Integration Tests ---

    @unittest.skipIf(not os.environ.get("TEST_MEDIA_DIR"), "TEST_MEDIA_DIR environment variable not set")
    def test_with_real_files_from_env(self):
        """Integration test using real files from the TEST_MEDIA_DIR."""
        real_media_dir = Path(os.environ["TEST_MEDIA_DIR"])
        
        real_files = [p for p in real_media_dir.glob("*.*") if p.is_file()][:5]
        if not real_files:
            self.skipTest(f"No files found in TEST_MEDIA_DIR: {real_media_dir}")

        temp_real_files = []
        for real_file in real_files:
            temp_path = self.source_dir / real_file.name
            shutil.copy(real_file, temp_path)
            temp_real_files.append(temp_path)

        search_results = [LizMediaSearchResult(status=MediaStatus.ACCEPTED, path=p) for p in temp_real_files]
        
        options = OrganizerOptions(copy=True, exif=True)
        organizer = MediaOrganizer(search_results, str(self.target_dir), options)
        organizer.organize()

        results = organizer.get_results()
        self.assertEqual(len(results), len(temp_real_files))
        
        for result in results:
            if result.success:
                self.assertTrue(Path(result.destination_path).exists())
                self.assertIn(str(result.media.year), result.destination_path)
        
        for temp_file in temp_real_files:
            self.assertTrue(temp_file.exists())

if __name__ == '__main__':
    unittest.main()