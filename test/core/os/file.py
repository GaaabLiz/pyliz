import json
import os
import tempfile
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

from pylizlib.core.domain.os import FileType
from pylizlib.core.os.file import (
    download_file,
    get_file_c_date,
    get_file_type,
    is_audio_extension,
    is_audio_file,
    is_file_dup_in_dir,
    is_image_extension,
    is_image_file,
    is_image_or_video_file,
    is_media_file,
    is_media_sidecar_file,
    is_text_extension,
    is_text_file,
    is_video_extension,
    is_video_file,
    write_json_to_file,
)


class IsExtensionTestCase(unittest.TestCase):
    # ── image ──
    def test_is_image_extension_png(self):
        self.assertTrue(is_image_extension(".png"))

    def test_is_image_extension_jpg(self):
        self.assertTrue(is_image_extension(".jpg"))

    def test_is_image_extension_heic(self):
        self.assertTrue(is_image_extension(".heic"))

    def test_is_image_extension_false(self):
        self.assertFalse(is_image_extension(".mp4"))

    # ── video ──
    def test_is_video_extension_mp4(self):
        self.assertTrue(is_video_extension(".mp4"))

    def test_is_video_extension_mov(self):
        self.assertTrue(is_video_extension(".mov"))

    def test_is_video_extension_false(self):
        self.assertFalse(is_video_extension(".png"))

    # ── audio ──
    def test_is_audio_extension_mp3(self):
        self.assertTrue(is_audio_extension(".mp3"))

    def test_is_audio_extension_flac(self):
        self.assertTrue(is_audio_extension(".flac"))

    def test_is_audio_extension_false(self):
        self.assertFalse(is_audio_extension(".jpg"))

    # ── text ──
    def test_is_text_extension_txt(self):
        self.assertTrue(is_text_extension(".txt"))

    def test_is_text_extension_pdf(self):
        self.assertTrue(is_text_extension(".pdf"))

    def test_is_text_extension_false(self):
        self.assertFalse(is_text_extension(".mp3"))


class IsFileTypeTestCase(unittest.TestCase):
    def test_is_image_file(self):
        self.assertTrue(is_image_file("/some/path/photo.jpg"))

    def test_is_image_file_false(self):
        self.assertFalse(is_image_file("/some/path/video.mp4"))

    def test_is_video_file(self):
        self.assertTrue(is_video_file("/some/path/clip.mov"))

    def test_is_video_file_false(self):
        self.assertFalse(is_video_file("/some/path/song.mp3"))

    def test_is_audio_file(self):
        self.assertTrue(is_audio_file("/music/track.flac"))

    def test_is_audio_file_false(self):
        self.assertFalse(is_audio_file("/music/track.png"))

    def test_is_text_file(self):
        self.assertTrue(is_text_file("/docs/readme.txt"))

    def test_is_text_file_false(self):
        self.assertFalse(is_text_file("/docs/readme.mp4"))

    def test_is_image_or_video_file_image(self):
        self.assertTrue(is_image_or_video_file("photo.png"))

    def test_is_image_or_video_file_video(self):
        self.assertTrue(is_image_or_video_file("clip.avi"))

    def test_is_image_or_video_file_false(self):
        self.assertFalse(is_image_or_video_file("song.mp3"))

    def test_is_media_file_image(self):
        self.assertTrue(is_media_file("photo.jpg"))

    def test_is_media_file_video(self):
        self.assertTrue(is_media_file("clip.mp4"))

    def test_is_media_file_audio(self):
        self.assertTrue(is_media_file("song.wav"))

    def test_is_media_file_false(self):
        self.assertFalse(is_media_file("readme.txt"))

    def test_is_media_sidecar_file_xmp(self):
        self.assertTrue(is_media_sidecar_file("photo.xmp"))

    def test_is_media_sidecar_file_aae(self):
        self.assertTrue(is_media_sidecar_file("photo.aae"))

    def test_is_media_sidecar_file_false(self):
        self.assertFalse(is_media_sidecar_file("photo.jpg"))


class GetFileTypeTestCase(unittest.TestCase):
    def test_get_file_type_image(self):
        self.assertEqual(get_file_type("photo.png"), FileType.IMAGE)

    def test_get_file_type_video(self):
        self.assertEqual(get_file_type("clip.mp4"), FileType.VIDEO)

    def test_get_file_type_audio(self):
        self.assertEqual(get_file_type("song.mp3"), FileType.AUDIO)

    def test_get_file_type_text(self):
        self.assertEqual(get_file_type("doc.pdf"), FileType.TEXT)

    def test_get_file_type_sidecar(self):
        self.assertEqual(get_file_type("photo.xmp"), FileType.MEDIA_SIDECAR)

    def test_get_file_type_unsupported_raises(self):
        with self.assertRaises(ValueError):
            get_file_type("archive.zip")


class IsFileDupInDirTestCase(unittest.TestCase):
    def test_file_found(self):
        with tempfile.TemporaryDirectory() as td:
            sub = os.path.join(td, "sub")
            os.makedirs(sub)
            open(os.path.join(sub, "hello.txt"), "w").close()
            self.assertTrue(is_file_dup_in_dir(td, "hello.txt"))

    def test_file_not_found(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertFalse(is_file_dup_in_dir(td, "nope.txt"))


class GetFileCDateTestCase(unittest.TestCase):
    def test_returns_datetime(self):
        with tempfile.NamedTemporaryFile() as tmp:
            result = get_file_c_date(tmp.name)
            self.assertIsInstance(result, datetime)


class DownloadFileTestCase(unittest.TestCase):
    @patch("pylizlib.core.os.file.logger")
    @patch("pylizlib.core.os.file.requests.get")
    def test_download_file_success(self, mock_get, mock_logger):
        mock_response = MagicMock()
        mock_response.headers = {"content-length": "3"}
        mock_response.iter_content.return_value = [b"abc"]
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        with tempfile.TemporaryDirectory() as td:
            dest = os.path.join(td, "file.bin")
            progress_values = []
            result = download_file("http://example.com/file", dest, progress_values.append)

            self.assertTrue(result.status)
            with open(dest, "rb") as f:
                self.assertEqual(f.read(), b"abc")

    @patch("pylizlib.core.os.file.requests.get", side_effect=Exception("network error"))
    def test_download_file_failure(self, mock_get):
        with tempfile.TemporaryDirectory() as td:
            dest = os.path.join(td, "file.bin")
            result = download_file("http://example.com/file", dest, lambda p: None)
            self.assertFalse(result.status)
            self.assertIn("network error", result.error)


class WriteJsonToFileTestCase(unittest.TestCase):
    def test_writes_valid_json(self):
        with tempfile.TemporaryDirectory() as td:
            content = {"key": "value", "number": 42}
            write_json_to_file(td, "data.json", content)

            file_path = os.path.join(td, "data.json")
            self.assertTrue(os.path.isfile(file_path))
            with open(file_path, "r") as f:
                self.assertEqual(json.load(f), content)

    def test_creates_missing_directory(self):
        with tempfile.TemporaryDirectory() as td:
            nested = os.path.join(td, "a", "b")
            write_json_to_file(nested, "out.json", {"x": 1})
            self.assertTrue(os.path.isfile(os.path.join(nested, "out.json")))


if __name__ == "__main__":
    unittest.main()
