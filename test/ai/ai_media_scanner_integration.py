import importlib.util
import unittest
from pathlib import Path

import requests
from PIL import Image

from pylizlib.ai import AiMediaScanner
from pylizlib.core.network.req import is_internet_available
from pylizlib.media.lizmedia import LizMedia

TEST_LOCAL_DIR = Path("/Users/gabliz/Developer/pyliz/test_local")
INTEGRATION_WORK_DIR = TEST_LOCAL_DIR / "ai_media_scanner_integration"

ASSETS = {
    "tags": {
        "filename": "tags_random_photo.jpg",
        "urls": [
            "https://picsum.photos/seed/pyliz-tags/640/480",
            "https://picsum.photos/seed/pyliz-tags-fallback/640/480",
        ],
    },
    "nsfw": {
        "filename": "nsfw_random_safe_photo.jpg",
        "urls": [
            "https://picsum.photos/seed/pyliz-nsfw/640/480",
            "https://picsum.photos/seed/pyliz-nsfw-fallback/640/480",
        ],
    },
    "ocr": {
        "filename": "ocr_text_image.png",
        "urls": [
            "https://dummyimage.com/800x240/ffffff/000000.png&text=PYLIZ+OCR+TEST+2026",
            "https://placehold.co/800x240/FFFFFF/000000.png?text=PYLIZ+OCR+TEST+2026",
        ],
        "expected_tokens": {"PYLIZ", "OCR", "TEST", "2026"},
    },
}


class AiMediaScannerIntegrationTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        INTEGRATION_WORK_DIR.mkdir(parents=True, exist_ok=True)

    def test_tags_with_downloaded_random_photo(self):
        self._require_internet()
        self._require_modules("torch", "torchvision", "huggingface_hub", "transformers", "einops")

        image_path = self._download_asset("tags")
        media = AiMediaScanner().scan(media_path=image_path, tools=["TAGS"])

        self.assertIsInstance(media, LizMedia)
        self.assertTrue(media.ai_scanned)
        self.assertEqual(media.ai_file_name, image_path.name)
        self.assertIsNotNone(media.ai_tags)
        self.assertGreater(len(media.ai_tags), 0)
        self.assertEqual(len(media.ai_tags), len(set(media.ai_tags)))

    def test_nsfw_with_downloaded_random_photo(self):
        self._require_internet()
        self._require_modules("nudenet")

        image_path = self._download_asset("nsfw")
        media = AiMediaScanner().scan(media_path=image_path, tools=["NSFW"])

        self.assertIsInstance(media, LizMedia)
        self.assertTrue(media.ai_scanned)
        self.assertIsInstance(media.ai_nsfw, bool)

    def test_ocr_with_downloaded_text_image(self):
        self._require_internet()
        self._require_modules("easyocr", "torch")

        image_path = self._download_asset("ocr")
        media = AiMediaScanner().scan(media_path=image_path, tools=["OCR"])

        self.assertIsInstance(media, LizMedia)
        self.assertTrue(media.ai_scanned)
        self.assertTrue(media.ai_has_ocr_text)
        self.assertIsNotNone(media.ai_ocr_text)
        self.assertGreater(len(media.ai_ocr_text), 0)

        extracted = " ".join(media.ai_ocr_text).upper()
        expected_tokens = ASSETS["ocr"]["expected_tokens"]
        found_tokens = {token for token in expected_tokens if token in extracted}
        self.assertGreaterEqual(len(found_tokens), 2)

    def _download_asset(self, asset_key: str) -> Path:
        asset = ASSETS[asset_key]
        target_path = INTEGRATION_WORK_DIR / asset["filename"]
        if self._is_valid_image(target_path):
            return target_path

        errors: list[str] = []
        for url in asset["urls"]:
            try:
                response = requests.get(url, timeout=30, allow_redirects=True)
                response.raise_for_status()
                target_path.write_bytes(response.content)
                if self._is_valid_image(target_path):
                    return target_path
                errors.append(f"Downloaded file from {url} is not a valid image")
            except Exception as exc:
                errors.append(f"{url}: {exc}")

        self.fail("Unable to download integration asset '" + asset_key + "': " + " | ".join(errors))

    def _require_internet(self):
        if not is_internet_available():
            self.skipTest("Internet non disponibile: skip dei test di integrazione AI.")

    def _require_modules(self, *modules: str):
        missing = [module for module in modules if importlib.util.find_spec(module) is None]
        if missing:
            self.skipTest("Dipendenze AI mancanti: " + ", ".join(missing))

    @staticmethod
    def _is_valid_image(path: Path) -> bool:
        if not path.exists() or path.stat().st_size == 0:
            return False
        try:
            with Image.open(path) as image:
                image.verify()
            return True
        except Exception:
            return False


if __name__ == "__main__":
    unittest.main()



