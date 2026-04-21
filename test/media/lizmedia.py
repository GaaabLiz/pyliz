import json
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, mock_open, patch

from pylizlib.core.domain.os import FileType
from pylizlib.media.lizmedia import LizMedia, LizMediaSearchResult, MediaListResult, MediaStatus


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
        mock_getsize.return_value = 1000000 # 1 MB decimal
        media = LizMedia(self.mock_path)
        
        self.assertEqual(media.size_byte, 1000000)
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
        with patch("builtins.open", mock_open(read_data=b"data")), \
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
    @patch("pylizlib.media.lizmedia.get_file_type", return_value=FileType.VIDEO)
    @patch("pylizlib.media.lizmedia.VideoUtils")
    def test_creation_date_video_metadata(self, mock_video_utils, _, __):
        media = LizMedia(self.mock_video_path)
        
        # Mock VideoUtils.get_video_creation_date to return a specific timestamp
        dt = datetime(2024, 3, 25, 10, 0, 0)
        mock_video_utils.get_video_creation_date.return_value = dt.timestamp()
        
        self.assertEqual(media.creation_date_from_exif_or_file_or_sidecar, dt)

    @patch("pylizlib.media.lizmedia.is_media_file", return_value=True)
    @patch("pylizlib.media.lizmedia.get_file_type", return_value=FileType.IMAGE)
    @patch("pylizlib.media.lizmedia.MetadataHandler")
    def test_creation_date_image_metadata_fallback(self, mock_handler_class, _, __):
        media = LizMedia(self.mock_path)
        
        dt = datetime(2024, 3, 25, 10, 0, 0)
        # Mocking the handler
        mock_handler = mock_handler_class.return_value
        mock_handler.get_image_creation_date.return_value = dt
        
        # When exifread fails (returns empty dictionary)
        with patch("pylizlib.media.lizmedia.exifread.process_file", return_value={}):
            self.assertEqual(media.creation_date_from_exif_or_file_or_sidecar, dt)

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
        meta_obj = MagicMock(spec="Metadata") #
        
        media.attach_eagle_metadata_path(meta_path)
        self.assertEqual(media.eagle_metadata_path, meta_path)
        
        media.attach_eagle_metadata(meta_obj)
        self.assertEqual(media.eagle_metadata, meta_obj)

    @patch("builtins.open", new_callable=mock_open, read_data=b"image-data")
    @patch("pylizlib.media.lizmedia.exifread.process_file", return_value={})
    @patch("pylizlib.media.lizmedia.MetadataHandler")
    @patch("pylizlib.media.lizmedia.ParserManager")
    @patch("os.path.getsize", return_value=2500000)
    @patch("pylizlib.media.lizmedia.get_file_c_date")
    @patch("pylizlib.media.lizmedia.get_file_type", return_value=FileType.IMAGE)
    @patch("pylizlib.media.lizmedia.is_media_file", return_value=True)
    def test_to_json_serializes_full_media_payload(
        self,
        _,
        __,
        mock_get_date,
        ___,
        mock_parser_manager,
        mock_metadata_handler,
        ____ ,
        _____,
    ):
        creation_dt = datetime(2024, 1, 2, 3, 4, 5)
        mock_get_date.return_value = creation_dt
        mock_parser_manager.return_value.parse.return_value = SimpleNamespace(prompt="a cat", steps=20)
        mock_metadata_handler.return_value.get_image_creation_date.return_value = None

        media = LizMedia(self.mock_path)
        media.attach_sidecar_file(Path("/path/to/test_image.xmp"))
        media.attach_sidecar_file(Path("/path/to/test_image.aae"))
        media.attach_eagle_metadata_path(Path("/path/to/metadata.json"))
        media.attach_eagle_metadata(SimpleNamespace(source="eagle", rating=5))
        media.base64_content = "YWJj"
        media.apply_ai_scan_result(
            tags=["cat", "art"],
            nsfw=False,
            ocr_text=["hello"],
            description="A cat image",
        )

        payload = json.loads(media.to_json())

        self.assertEqual(payload["path"], "/path/to/test_image.jpg")
        self.assertEqual(payload["file_name"], "test_image.jpg")
        self.assertEqual(payload["extension"], ".jpg")
        self.assertEqual(payload["creation_time"], creation_dt.isoformat())
        self.assertEqual(payload["creation_time_timestamp"], creation_dt.timestamp())
        self.assertEqual(payload["creation_date_from_exif_or_file_or_sidecar"], creation_dt.isoformat())
        self.assertEqual(payload["year"], 2024)
        self.assertEqual(payload["month"], 1)
        self.assertEqual(payload["day"], 2)
        self.assertEqual(payload["size_byte"], 2500000)
        self.assertEqual(payload["size_mb"], 2.5)
        self.assertEqual(payload["type"], FileType.IMAGE.value)
        self.assertTrue(payload["is_image"])
        self.assertFalse(payload["is_video"])
        self.assertFalse(payload["is_audio"])
        self.assertEqual(payload["stable_diffusion_metadata"], {"prompt": "a cat", "steps": 20})
        self.assertFalse(payload["has_exif_data"])
        self.assertTrue(payload["ai_generated"])
        self.assertIsNone(payload["duration_sec"])
        self.assertIsNone(payload["duration_min"])
        self.assertIsNone(payload["frame_rate"])
        self.assertEqual(payload["eagle_metadata_path"], "/path/to/metadata.json")
        self.assertEqual(payload["eagle_metadata"], {"source": "eagle", "rating": 5})
        self.assertEqual(
            payload["attached_sidecar_files"],
            ["/path/to/test_image.xmp", "/path/to/test_image.aae"],
        )
        self.assertTrue(payload["has_xmp_sidecar"])
        self.assertTrue(payload["has_aae_sidecar"])
        self.assertEqual(payload["xmp_sidecar"], "/path/to/test_image.xmp")
        self.assertEqual(payload["base64_content"], "YWJj")
        self.assertEqual(payload["ai_ocr_text"], ["hello"])
        self.assertTrue(payload["ai_has_ocr_text"])
        self.assertEqual(payload["ai_file_name"], "test_image.jpg")
        self.assertEqual(payload["ai_description"], "A cat image")
        self.assertEqual(payload["ai_desc_plus_text"], "A cat image This media includes texts: hello")
        self.assertEqual(payload["ai_tags"], ["cat", "art"])
        self.assertTrue(payload["ai_scanned"])
        self.assertFalse(payload["ai_nsfw"])

    @patch("os.path.getsize", return_value=4096)
    @patch("pylizlib.media.lizmedia.get_file_c_date")
    @patch("pylizlib.media.lizmedia.get_file_type", return_value=FileType.AUDIO)
    @patch("pylizlib.media.lizmedia.is_media_file", return_value=True)
    def test_to_json_uses_null_for_unavailable_media_values(self, _, __, mock_get_date, ___):
        creation_dt = datetime(2025, 6, 7, 8, 9, 10)
        mock_get_date.return_value = creation_dt

        media = LizMedia(Path("/path/to/test_audio.mp3"))
        payload = json.loads(media.to_json())

        self.assertEqual(payload["path"], "/path/to/test_audio.mp3")
        self.assertEqual(payload["creation_time"], creation_dt.isoformat())
        self.assertEqual(payload["type"], FileType.AUDIO.value)
        self.assertFalse(payload["is_image"])
        self.assertFalse(payload["is_video"])
        self.assertTrue(payload["is_audio"])
        self.assertIsNone(payload["stable_diffusion_metadata"])
        self.assertIsNone(payload["has_exif_data"])
        self.assertIsNone(payload["ai_generated"])
        self.assertIsNone(payload["duration_sec"])
        self.assertIsNone(payload["duration_min"])
        self.assertIsNone(payload["frame_rate"])
        self.assertIsNone(payload["eagle_metadata_path"])
        self.assertIsNone(payload["eagle_metadata"])
        self.assertIsNone(payload["xmp_sidecar"])
        self.assertIsNone(payload["base64_content"])
        self.assertIsNone(payload["ai_ocr_text"])
        self.assertIsNone(payload["ai_has_ocr_text"])
        self.assertIsNone(payload["ai_file_name"])
        self.assertIsNone(payload["ai_description"])
        self.assertIsNone(payload["ai_desc_plus_text"])
        self.assertIsNone(payload["ai_tags"])
        self.assertFalse(payload["ai_scanned"])
        self.assertIsNone(payload["ai_nsfw"])

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
