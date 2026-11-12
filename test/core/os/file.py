import json
import os
import tempfile
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

from pylizlib.core.domain.os import FileType
from pylizlib.core.network.download import download_file
from pylizlib.core.os.filesystem.file_types import (
    get_file_type,
    is_audio_extension,
    is_audio_file,
    is_image_extension,
    is_image_file,
    is_image_or_video_file,
    is_media_file,
    is_media_sidecar_file,
    is_text_extension,
    is_text_file,
    is_video_extension,
    is_video_file,
)
from pylizlib.core.os.filesystem.files import get_file_c_date, is_file_dup_in_dir
from pylizlib.core.os.filesystem.json import write_json_to_file


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

    def test_image_extensions_are_case_insensitive(self):
        self.assertTrue(is_image_extension(".JPG"))
        self.assertTrue(is_image_extension(".PnG"))

    # ── video ──
    def test_is_video_extension_mp4(self):
        self.assertTrue(is_video_extension(".mp4"))

    def test_is_video_extension_mov(self):
        self.assertTrue(is_video_extension(".mov"))

    def test_is_video_extension_false(self):
        self.assertFalse(is_video_extension(".png"))

    def test_video_extension_is_case_insensitive(self):
        self.assertTrue(is_video_extension(".MP4"))

    # ── audio ──
    def test_is_audio_extension_mp3(self):
        self.assertTrue(is_audio_extension(".mp3"))

    def test_is_audio_extension_flac(self):
        self.assertTrue(is_audio_extension(".flac"))

    def test_is_audio_extension_false(self):
        self.assertFalse(is_audio_extension(".jpg"))

    def test_audio_extension_is_case_insensitive(self):
        self.assertTrue(is_audio_extension(".FlAc"))

    # ── text ──
    def test_is_text_extension_txt(self):
        self.assertTrue(is_text_extension(".txt"))

    def test_is_text_extension_pdf(self):
        self.assertTrue(is_text_extension(".pdf"))

    def test_is_text_extension_false(self):
        self.assertFalse(is_text_extension(".mp3"))

    def test_text_extension_is_case_insensitive(self):
        self.assertTrue(is_text_extension(".PDF"))


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

    def test_media_path_extensions_are_case_insensitive(self):
        self.assertTrue(is_image_file("/media/photo.JpG"))
        self.assertTrue(is_video_file("/media/clip.MP4"))
        self.assertTrue(is_audio_file("/media/song.FlAc"))
        self.assertTrue(is_media_sidecar_file("/media/photo.XmP"))

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

    def test_media_sidecar_extensions_are_case_insensitive(self):
        self.assertTrue(is_media_sidecar_file("photo.XmP"))
        self.assertTrue(is_media_sidecar_file("photo.XML"))

    def test_is_media_sidecar_file_false(self):
        self.assertFalse(is_media_sidecar_file("photo.jpg"))


class GetFileTypeTestCase(unittest.TestCase):
    def test_get_file_type_image(self):
        self.assertEqual(get_file_type("photo.png"), FileType.IMAGE)

    def test_get_file_type_video(self):
        self.assertEqual(get_file_type("clip.mp4"), FileType.VIDEO)

    def test_get_file_type_accepts_uppercase_extensions(self):
        self.assertEqual(get_file_type("photo.JpG"), FileType.IMAGE)
        self.assertEqual(get_file_type("clip.MP4"), FileType.VIDEO)
        self.assertEqual(get_file_type("photo.XmP"), FileType.MEDIA_SIDECAR)

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

    def test_returns_datetime_windows(self):
        with tempfile.NamedTemporaryFile() as tmp:
            with patch("pylizlib.core.os.filesystem.files.platform.system", return_value="Windows"):
                with patch("pylizlib.core.os.filesystem.files.os.path.getctime", return_value=1700000000.0) as mock_ctime:
                    result = get_file_c_date(tmp.name)
                    self.assertIsInstance(result, datetime)
                    mock_ctime.assert_called_once_with(tmp.name)

    def test_returns_datetime_linux_without_birthtime(self):
        with tempfile.NamedTemporaryFile() as tmp:
            with patch("pylizlib.core.os.filesystem.files.platform.system", return_value="Linux"):
                mock_stat = MagicMock(spec=["st_mtime"])
                mock_stat.st_mtime = 1700000000.0
                with patch("pylizlib.core.os.filesystem.files.os.stat", return_value=mock_stat):
                    result = get_file_c_date(tmp.name)
                    self.assertIsInstance(result, datetime)


class DownloadFileTestCase(unittest.TestCase):
    @patch("pylizlib.core.network.download.requests.get")
    def test_download_file_success_uses_real_logger(self, mock_get):
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

    @patch("pylizlib.core.network.download.requests.get", side_effect=Exception("network error"))
    def test_download_file_failure(self, mock_get):
        with tempfile.TemporaryDirectory() as td:
            dest = os.path.join(td, "file.bin")
            result = download_file("http://example.com/file", dest, lambda p: None)
            self.assertFalse(result.status)
            self.assertIn("network error", result.error)

    @patch("pylizlib.core.network.download.logger")
    @patch("pylizlib.core.network.download.requests.get")
    def test_download_without_content_length_succeeds_and_replaces_atomically(self, mock_get, _mock_logger):
        response = MagicMock()
        response.headers = {}
        response.iter_content.return_value = [b"new content"]
        mock_get.return_value = response

        with tempfile.TemporaryDirectory() as td:
            dest = os.path.join(td, "file.bin")
            with open(dest, "wb") as file:
                file.write(b"old content")
            progress_values = []

            result = download_file("https://example.com/file", dest, progress_values.append)

            self.assertTrue(result.status)
            with open(dest, "rb") as file:
                self.assertEqual(file.read(), b"new content")
            self.assertEqual(progress_values, [100])
            mock_get.assert_called_once_with("https://example.com/file", stream=True, timeout=30)
            response.close.assert_called_once()

    @patch("pylizlib.core.network.download.logger")
    @patch("pylizlib.core.network.download.requests.get")
    def test_interrupted_download_preserves_existing_file(self, mock_get, _mock_logger):
        response = MagicMock()
        response.headers = {"content-length": "100"}

        def interrupted_chunks(chunk_size):
            yield b"partial"
            raise OSError("connection dropped")

        response.iter_content.side_effect = interrupted_chunks
        mock_get.return_value = response

        with tempfile.TemporaryDirectory() as td:
            dest = os.path.join(td, "file.bin")
            with open(dest, "wb") as file:
                file.write(b"keep this file")

            result = download_file("https://example.com/file", dest, lambda _: None)

            self.assertFalse(result.status)
            self.assertIn("connection dropped", result.error)
            with open(dest, "rb") as file:
                self.assertEqual(file.read(), b"keep this file")
            self.assertFalse(any(name.startswith(".download-") for name in os.listdir(td)))
            response.close.assert_called_once()


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

    def test_serialization_error_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as td:
            file_path = os.path.join(td, "data.json")
            with open(file_path, "w", encoding="utf-8") as file:
                file.write('{"keep": true}')

            with self.assertRaises(TypeError):
                write_json_to_file(td, "data.json", {"created": datetime.now()})

            with open(file_path, encoding="utf-8") as file:
                self.assertEqual(file.read(), '{"keep": true}')

    @patch("pylizlib.core.os.filesystem.json.os.fsync", side_effect=OSError("disk write failed"))
    def test_write_error_preserves_existing_file(self, _mock_fsync):
        with tempfile.TemporaryDirectory() as td:
            file_path = os.path.join(td, "data.json")
            with open(file_path, "w", encoding="utf-8") as file:
                file.write('{"keep": true}')

            with self.assertRaisesRegex(OSError, "disk write failed"):
                write_json_to_file(td, "data.json", {"replace": True})

            with open(file_path, encoding="utf-8") as file:
                self.assertEqual(file.read(), '{"keep": true}')
            self.assertEqual(os.listdir(td), ["data.json"])


if __name__ == "__main__":
    unittest.main()
