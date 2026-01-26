import unittest
from unittest.mock import MagicMock, patch, mock_open
from pathlib import Path
from datetime import datetime
import os

from pylizlib.media.lizmedia import LizMedia, LizMediaSearchResult, MediaListResult, MediaStatus
from pylizlib.core.domain.os import FileType
from pylizlib.eaglecool.model.metadata import Metadata

class TestLizMedia(unittest.TestCase):

    def setUp(self):
        self.mock_path = Path("/path/to/test_image.jpg")
        self.mock_video_path = Path("/path/to/test_video.mp4")

    @patch("pylizlib.media.lizmedia.is_media_file")
    def test_initialization_valid_media(self, mock_is_media):
        mock_is_media.return_value = True
        media = LizMedia(self.mock_path)
        self.assertEqual(media.path, self.mock_path)

    @patch("pylizlib.media.lizmedia.is_media_file")
    def test_initialization_invalid(self, mock_is_media):
        mock_is_media.return_value = False
        with self.assertRaises(ValueError):
            LizMedia(Path("/path/to/invalid.txt"))

    @patch("pylizlib.media.lizmedia.is_media_file")
    def test_initialization_sidecar_should_fail(self, mock_is_media):
        # LizMedia is for media files only, not sidecars directly
        mock_is_media.return_value = False
        with self.assertRaises(ValueError):
            LizMedia(Path("/path/to/test.xmp"))

    @patch("pylizlib.media.lizmedia.is_media_file", return_value=True)
    def test_properties_general(self, _):
        media = LizMedia(self.mock_path)
        self.assertEqual(media.file_name, "test_image.jpg")
        self.assertEqual(media.extension, ".jpg")

    @patch("pylizlib.media.lizmedia.is_media_file", return_value=True)
    @patch("pylizlib.media.lizmedia.get_file_c_date")
    def test_creation_time(self, mock_get_date, _):
        dt = datetime(2023, 1, 1, 12, 0, 0)
        mock_get_date.return_value = dt
        media = LizMedia(self.mock_path)
        
        self.assertEqual(media.creation_time, dt)
        self.assertEqual(media.creation_time_timestamp, dt.timestamp())
        self.assertEqual(media.year, 2023)
        self.assertEqual(media.month, 1)
        self.assertEqual(media.day, 1)

    @patch("pylizlib.media.lizmedia.is_media_file", return_value=True)
    @patch("os.path.getsize")
    def test_size(self, mock_getsize, _):
        mock_getsize.return_value = 1048576 # 1 MB
        media = LizMedia(self.mock_path)
        
        self.assertEqual(media.size_byte, 1048576)
        self.assertEqual(media.size_mb, 1.0)

    @patch("pylizlib.media.lizmedia.is_media_file", return_value=True)
    @patch("pylizlib.media.lizmedia.get_file_type")
    def test_type_checks(self, mock_get_type, _):
        media = LizMedia(self.mock_path)
        
        mock_get_type.return_value = FileType.IMAGE
        self.assertTrue(media.is_image)
        self.assertFalse(media.is_video)
        
        mock_get_type.return_value = FileType.VIDEO
        self.assertTrue(media.is_video)
        self.assertFalse(media.is_image)

    @patch("pylizlib.media.lizmedia.is_media_file", return_value=True)
    @patch("pylizlib.media.lizmedia.get_file_type", return_value=FileType.IMAGE)
    @patch("pylizlib.media.lizmedia.ParserManager")
    def test_stable_diffusion_metadata(self, mock_parser_manager, _, __):
        media = LizMedia(self.mock_path)
        
        # Test found
        mock_instance = mock_parser_manager.return_value
        mock_instance.parse.return_value = "Prompt Data"
        self.assertEqual(media.stable_diffusion_metadata, "Prompt Data")
        self.assertTrue(media.ai_generated)
        
        # Test not found
        mock_instance.parse.return_value = None
        self.assertIsNone(media.stable_diffusion_metadata)
        self.assertFalse(media.ai_generated)

    @patch("pylizlib.media.lizmedia.is_media_file", return_value=True)
    @patch("pylizlib.media.lizmedia.get_file_type", return_value=FileType.IMAGE)
    def test_exif_data(self, _, __):
        media = LizMedia(self.mock_path)
        
        # Mocking open and exifread
        with patch("builtins.open", mock_open(read_data=b"data")) as mock_file, \
             patch("pylizlib.media.lizmedia.exifread.process_file") as mock_exif:
            
            # Case 1: EXIF found with DateTimeOriginal
            mock_exif.return_value = {'EXIF DateTimeOriginal': '2022:12:31 10:00:00'}
            self.assertTrue(media.has_exif_data)
            self.assertEqual(media.creation_date_from_exif_or_file_or_sidecar, datetime(2022, 12, 31, 10, 0, 0))
            
            # Case 2: No EXIF found, fallback to file date
            mock_exif.return_value = {}
            # Mocking creation_time property logic locally since property is cached/computed
            with patch.object(LizMedia, 'creation_time', datetime(2023, 1, 1)):
                self.assertFalse(media.has_exif_data)
                self.assertEqual(media.creation_date_from_exif_or_file_or_sidecar, datetime(2023, 1, 1))

    @patch("pylizlib.media.lizmedia.is_media_file", return_value=True)
    @patch("pylizlib.media.lizmedia.get_file_type", return_value=FileType.IMAGE)
    def test_creation_date_xmp_priority(self, _, __):
        media = LizMedia(self.mock_path)
        
        # Attach XMP sidecar
        xmp_path = Path("/path/to/test.xmp")
        media.attach_sidecar_file(xmp_path)
        
        # Mock file reading for XMP
        xmp_content = '<photoshop:DateCreated>2021-05-20T15:30:00</photoshop:DateCreated>'
        
        # We need to mock open, Path.exists and exifread to simulate "no exif"
        with patch("pathlib.Path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=xmp_content)), \
             patch("pylizlib.media.lizmedia.exifread.process_file", return_value={}):
             
             # Should prioritize XMP (2021) over file time (default mock)
             self.assertEqual(media.creation_date_from_exif_or_file_or_sidecar, datetime(2021, 5, 20, 15, 30, 0))

    @patch("pylizlib.media.lizmedia.is_media_file", return_value=True)
    @patch("pylizlib.media.lizmedia.get_file_type", return_value=FileType.VIDEO)
    @patch("pylizlib.media.lizmedia.VideoUtils")
    def test_video_properties(self, mock_video_utils, _, __):
        media = LizMedia(self.mock_video_path)
        
        mock_video_utils.get_video_duration_seconds.return_value = 120.0
        mock_video_utils.get_video_frame_rate.return_value = 30.0
        
        self.assertEqual(media.duration_sec, 120.0)
        self.assertEqual(media.duration_min, 2.0)
        self.assertEqual(media.frame_rate, 30.0)

    @patch("pylizlib.media.lizmedia.is_media_file", return_value=True)
    def test_sidecar_management(self, _):
        media = LizMedia(self.mock_path)
        xmp = Path("test.xmp")
        aae = Path("test.aae")
        
        media.attach_sidecar_file(xmp)
        self.assertIn(xmp, media.attached_sidecar_files)
        self.assertTrue(media.has_xmp_sidecar())
        self.assertEqual(media.get_xmp_sidecar(), xmp)
        self.assertFalse(media.has_aae_sidecar())
        
        media.attach_sidecar_file(aae)
        self.assertTrue(media.has_aae_sidecar())
        
        media.detach_sidecar_file(xmp)
        self.assertNotIn(xmp, media.attached_sidecar_files)
        
        media.clear_sidecar_files()
        self.assertEqual(len(media.attached_sidecar_files), 0)

    @patch("pylizlib.media.lizmedia.is_media_file", return_value=True)
    def test_eagle_metadata(self, _):
        media = LizMedia(self.mock_path)
        meta_path = Path("metadata.json")
        meta_obj = MagicMock(spec=Metadata)
        
        media.attach_eagle_metadata_path(meta_path)
        self.assertEqual(media.eagle_metadata_path, meta_path)
        
        media.attach_eagle_metadata(meta_obj)
        self.assertEqual(media.eagle_metadata, meta_obj)

class TestLizMediaSearchResult(unittest.TestCase):
    
    def test_initialization_and_properties(self):
        res1 = LizMediaSearchResult(MediaStatus.ACCEPTED, Path("p1"))
        res2 = LizMediaSearchResult(MediaStatus.REJECTED, Path("p2"))
        
        # Check auto-increment index
        self.assertTrue(res1.index < res2.index)
        
        # Check defaults
        self.assertIsNone(res1.media)
        self.assertFalse(res1.has_lizmedia())
        self.assertFalse(res1.has_sidecars())
        
        # Check with media and sidecars
        mock_media = MagicMock(spec=LizMedia)
        mock_media.attached_sidecar_files = [Path("s1")]
        
        res3 = LizMediaSearchResult(MediaStatus.ACCEPTED, Path("p3"), media=mock_media)
        self.assertTrue(res3.has_lizmedia())
        self.assertTrue(res3.has_sidecars())

class TestMediaListResult(unittest.TestCase):
    
    def test_total_count(self):
        res = MediaListResult()
        res.accepted.append(LizMediaSearchResult(MediaStatus.ACCEPTED, Path("a")))
        res.rejected.append(LizMediaSearchResult(MediaStatus.REJECTED, Path("r")))
        res.errored.append(LizMediaSearchResult(MediaStatus.REJECTED, Path("e")))
        
        self.assertEqual(res.total_count, 3)

if __name__ == '__main__':
    unittest.main()
