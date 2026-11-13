import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests

from pylizlib.core.testing.sample_downloader import SampleImageDownloader


class SampleImageDownloaderTestCase(unittest.TestCase):
    def test_init_without_cache(self):
        downloader = SampleImageDownloader()
        self.assertIsNone(downloader.cache_dir)

    def test_init_with_cache_creates_directory(self):
        with tempfile.TemporaryDirectory() as td:
            cache_path = Path(td) / "cache" / "images"
            downloader = SampleImageDownloader(cache_dir=cache_path)
            self.assertTrue(cache_path.is_dir())
            self.assertEqual(downloader.cache_dir, cache_path)

    @patch("pylizlib.core.testing.sample_downloader.requests.get")
    def test_download_image_url_variations(self, mock_get):
        mock_response = MagicMock()
        mock_response.content = b"fake-image-bytes"
        mock_get.return_value = mock_response

        downloader = SampleImageDownloader()
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "img.jpg"

            # 1. with image_id
            downloader.download_image(dest, width=100, height=80, image_id=42)
            mock_get.assert_called_with("https://picsum.photos/id/42/100/80", timeout=15)
            self.assertEqual(dest.read_bytes(), b"fake-image-bytes")

            # 2. with seed
            downloader.download_image(dest, width=120, height=90, seed="test_seed")
            mock_get.assert_called_with("https://picsum.photos/seed/test_seed/120/90", timeout=15)

            # 3. pure random
            downloader.download_image(dest, width=50, height=50)
            mock_get.assert_called_with("https://picsum.photos/50/50", timeout=15)

            # 4. with grayscale
            downloader.download_image(dest, width=50, height=50, grayscale=True)
            mock_get.assert_called_with("https://picsum.photos/50/50?grayscale", timeout=15)

    @patch("pylizlib.core.testing.sample_downloader.requests.get")
    def test_download_image_cache_hit_and_miss(self, mock_get):
        mock_response = MagicMock()
        mock_response.content = b"downloaded-bytes"
        mock_get.return_value = mock_response

        with tempfile.TemporaryDirectory() as td:
            cache_dir = Path(td) / "cache"
            downloader = SampleImageDownloader(cache_dir=cache_dir)
            dest1 = Path(td) / "dest1" / "img.jpg"

            # First download (cache miss)
            url = "https://picsum.photos/seed/hit_test/200/200"
            cache_key = hashlib.md5(url.encode()).hexdigest()
            cache_file = cache_dir / f"{cache_key}.jpg"

            result1 = downloader.download_image(dest1, seed="hit_test")
            self.assertEqual(result1, dest1)
            self.assertEqual(dest1.read_bytes(), b"downloaded-bytes")
            self.assertTrue(cache_file.exists())
            self.assertEqual(cache_file.read_bytes(), b"downloaded-bytes")
            self.assertEqual(mock_get.call_count, 1)

            # Second download (cache hit)
            dest2 = Path(td) / "dest2" / "img.jpg"
            result2 = downloader.download_image(dest2, seed="hit_test")
            self.assertEqual(result2, dest2)
            self.assertEqual(dest2.read_bytes(), b"downloaded-bytes")
            # mock_get should not be called again!
            self.assertEqual(mock_get.call_count, 1)

    @patch("pylizlib.core.testing.sample_downloader.requests.get", side_effect=requests.RequestException("download error"))
    def test_download_image_raises_request_exception(self, _mock_get):
        downloader = SampleImageDownloader()
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "img.jpg"
            with self.assertRaises(requests.RequestException):
                downloader.download_image(dest)

    @patch("pylizlib.core.testing.sample_downloader.requests.get")
    def test_download_image_raises_http_error_response(self, mock_get):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("404 Not Found")
        mock_get.return_value = mock_response

        downloader = SampleImageDownloader()
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(requests.HTTPError):
                downloader.download_image(Path(td) / "missing.jpg")

    @patch("pylizlib.core.testing.sample_downloader.requests.get")
    def test_download_images_to_folder(self, mock_get):
        mock_response = MagicMock()
        mock_response.content = b"image-data"
        mock_get.return_value = mock_response

        downloader = SampleImageDownloader()
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td) / "images"
            seeds = ["seed_0", "seed_1"]
            downloaded = downloader.download_images_to_folder(
                folder=folder,
                count=3,
                width=100,
                height=100,
                prefix="pic",
                seeds=seeds,
            )
            self.assertEqual(len(downloaded), 3)
            self.assertTrue((folder / "pic_0.jpg").exists())
            self.assertTrue((folder / "pic_1.jpg").exists())
            self.assertTrue((folder / "pic_2.jpg").exists())

    @patch("pylizlib.core.testing.sample_downloader.requests.get")
    def test_download_images_to_folder_keeps_successes_after_partial_request_failures(self, mock_get):
        success = MagicMock(content=b"image-data")
        success.raise_for_status.return_value = None
        failure = MagicMock()
        failure.raise_for_status.side_effect = requests.RequestException("connection failed")
        mock_get.side_effect = [success, failure, success]

        downloader = SampleImageDownloader()
        with tempfile.TemporaryDirectory() as td:
            downloaded = downloader.download_images_to_folder(Path(td) / "images", count=3)

        self.assertEqual(len(downloaded), 2)
        self.assertEqual([path.read_bytes() for path in downloaded], [b"image-data", b"image-data"])

    @patch.object(SampleImageDownloader, "download_image")
    def test_download_images_to_folder_handles_error(self, mock_download):
        mock_download.side_effect = [Path("/img0.jpg"), RuntimeError("failed"), Path("/img2.jpg")]

        downloader = SampleImageDownloader()
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td) / "images"
            with patch("pylizlib.core.testing.sample_downloader.logger.error") as mock_log:
                downloaded = downloader.download_images_to_folder(folder=folder, count=3)
                self.assertEqual(len(downloaded), 2)
                mock_log.assert_called_once()

    @patch.object(SampleImageDownloader, "download_images_to_folder")
    def test_create_sample_directory(self, mock_download_folder):
        downloader = SampleImageDownloader()
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            extra_files = {"notes.txt": "some notes", "readme.md": "# Readme"}
            dir_path = downloader.create_sample_directory(
                base_path=base,
                dir_name="sample_dir",
                image_count=2,
                extra_text_files=extra_files,
            )
            self.assertEqual(dir_path, base / "sample_dir")
            self.assertTrue(dir_path.is_dir())
            mock_download_folder.assert_called_once()
            self.assertEqual((dir_path / "notes.txt").read_text(encoding="utf-8"), "some notes")
            self.assertEqual((dir_path / "readme.md").read_text(encoding="utf-8"), "# Readme")


if __name__ == "__main__":
    unittest.main()
