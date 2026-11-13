import base64
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pylizlib.media.domain.source import ResolvedMediaSource
from pylizlib.media.util.source import resolve_media_source


class TestMediaSourceUtils(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="pyliz_media_source_")
        self.image_path = Path(self.temp_dir.name) / "source.png"
        Image.new("RGB", (3, 3), color=(10, 20, 30)).save(self.image_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_resolve_media_source_from_path(self):
        source = resolve_media_source(media_path=self.image_path)

        self.assertIsInstance(source, ResolvedMediaSource)
        self.assertEqual(source.path, self.image_path.resolve())
        self.assertFalse(source.is_temporary)
        self.assertIsNone(source.base64_content)

    def test_resolve_media_source_from_data_uri(self):
        payload = base64.b64encode(self.image_path.read_bytes()).decode("utf-8")
        source = resolve_media_source(base64_content=f"data:image/png;base64,{payload}")
        try:
            self.assertTrue(source.is_temporary)
            self.assertEqual(source.path.suffix, ".png")
            self.assertTrue(source.path.exists())
        finally:
            source.path.unlink(missing_ok=True)

    def test_resolve_media_source_requires_hint_for_unknown_base64(self):
        payload = base64.b64encode(b"not-an-image").decode("utf-8")
        with self.assertRaises(ValueError):
            resolve_media_source(base64_content=payload)


if __name__ == "__main__":
    unittest.main()
