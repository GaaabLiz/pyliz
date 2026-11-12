import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests

from pylizlib.core.testing.sample_downloader import SampleImageDownloader


class SampleImageDownloaderTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="pyliz_test_downloader_")
        self.base_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_init_creates_cache_dir(self):
        cache_dir = self.base_path / "cache_folder"
        self.assertFalse(cache_dir.exists())
        downloader = SampleImageDownloader(cache_dir=cache_dir)
        self.assertTrue(cache_dir.exists())
        self.assertEqual(downloader.cache_dir, cache_dir)

    @patch("requests.get")
    def test_download_image_default_url(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.content = b"fake_image_bytes"
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        downloader = SampleImageDownloader()
        dest = self.base_path / "out" / "img.jpg"
        result = downloader.download_image(dest, width=100, height=150)

        self.assertEqual(result, dest)
        self.assertTrue(dest.exists())
        self.assertEqual(dest.read_bytes(), b"fake_image_bytes")
        mock_get.assert_called_once_with("https://picsum.photos/100/150", timeout=15)

    @patch("requests.get")
    def test_download_image_with_id_and_grayscale(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.content = b"fake_id_bytes"
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        downloader = SampleImageDownloader()
        dest = self.base_path / "img_id.jpg"
        downloader.download_image(dest, width=200, height=200, image_id=42, grayscale=True)

        mock_get.assert_called_once_with("https://picsum.photos/id/42/200/200?grayscale", timeout=15)

    @patch("requests.get")
    def test_download_image_with_seed(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.content = b"fake_seed_bytes"
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        downloader = SampleImageDownloader()
        dest = self.base_path / "img_seed.jpg"
        downloader.download_image(dest, width=50, height=50, seed="my_seed")

        mock_get.assert_called_once_with("https://picsum.photos/seed/my_seed/50/50", timeout=15)

    @patch("requests.get")
    def test_download_image_caching(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.content = b"cached_content"
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        cache_dir = self.base_path / "cache"
        downloader = SampleImageDownloader(cache_dir=cache_dir)

        dest1 = self.base_path / "first.jpg"
        dest2 = self.base_path / "second.jpg"

        # First call: cache miss -> network call
        res1 = downloader.download_image(dest1, width=120, height=120, seed="test_cache")
        self.assertEqual(mock_get.call_count, 1)
        self.assertEqual(res1.read_bytes(), b"cached_content")

        # Second call: cache hit -> no additional network call
        res2 = downloader.download_image(dest2, width=120, height=120, seed="test_cache")
        self.assertEqual(mock_get.call_count, 1)
        self.assertEqual(res2.read_bytes(), b"cached_content")

    @patch("requests.get")
    def test_download_image_raises_on_error(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError("404 Not Found")
        mock_get.return_value = mock_resp

        downloader = SampleImageDownloader()
        dest = self.base_path / "error.jpg"
        with self.assertRaises(requests.exceptions.HTTPError):
            downloader.download_image(dest)

    @patch("requests.get")
    def test_download_images_to_folder(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.content = b"image_data"
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        downloader = SampleImageDownloader()
        folder = self.base_path / "gallery"
        custom_seeds = ["seed_a", "seed_b"]
        downloaded = downloader.download_images_to_folder(folder, count=3, seeds=custom_seeds)

        self.assertEqual(len(downloaded), 3)
        self.assertEqual(mock_get.call_count, 3)
        self.assertTrue((folder / "image_0.jpg").exists())
        self.assertTrue((folder / "image_1.jpg").exists())
        self.assertTrue((folder / "image_2.jpg").exists())

    @patch("requests.get")
    def test_download_images_to_folder_handles_partial_failures(self, mock_get):
        success_resp = MagicMock()
        success_resp.content = b"success"
        success_resp.raise_for_status.return_value = None

        error_resp = MagicMock()
        error_resp.raise_for_status.side_effect = requests.exceptions.RequestException("Conn error")

        mock_get.side_effect = [success_resp, error_resp, success_resp]

        downloader = SampleImageDownloader()
        folder = self.base_path / "gallery_fail"
        downloaded = downloader.download_images_to_folder(folder, count=3)

        self.assertEqual(len(downloaded), 2)

    @patch("requests.get")
    def test_create_sample_directory(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.content = b"img_data"
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        downloader = SampleImageDownloader()
        dir_path = downloader.create_sample_directory(
            base_path=self.base_path,
            dir_name="sample_dir",
            image_count=2,
            extra_text_files={"notes.txt": "hello world", "config.json": "{}"},
        )

        self.assertTrue(dir_path.exists())
        self.assertTrue((dir_path / "image_0.jpg").exists())
        self.assertTrue((dir_path / "image_1.jpg").exists())
        self.assertEqual((dir_path / "notes.txt").read_text(encoding="utf-8"), "hello world")
        self.assertEqual((dir_path / "config.json").read_text(encoding="utf-8"), "{}")


if __name__ == "__main__":
    unittest.main()
