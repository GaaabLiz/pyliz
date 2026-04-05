import base64
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pylizlib.ai import AiMediaScanner, AiScanResult, AiScanTool
from pylizlib.media.lizmedia import LizMedia


class _StaticProvider:
    def __init__(self, tool: AiScanTool, result: AiScanResult):
        self.tool = tool
        self.result = result
        self.calls = 0

    def scan(self, media: LizMedia) -> AiScanResult:
        self.calls += 1
        return self.result


class _FailingProvider:
    tool = AiScanTool.TAGS

    def scan(self, media: LizMedia) -> AiScanResult:
        raise RuntimeError("boom")


class AiMediaScannerTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="pyliz_ai_test_")
        self.image_path = Path(self.temp_dir.name) / "sample.png"
        Image.new("RGB", (4, 4), color=(255, 0, 0)).save(self.image_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_scan_from_path_applies_requested_results(self):
        tags_provider = _StaticProvider(AiScanTool.TAGS, AiScanResult(tags=["cat", "indoor"]))
        nsfw_provider = _StaticProvider(AiScanTool.NSFW, AiScanResult(nsfw=False))
        ocr_provider = _StaticProvider(AiScanTool.OCR, AiScanResult(ocr_text=["HELLO"], ocr_detected=True))
        scanner = AiMediaScanner(providers=[tags_provider, nsfw_provider, ocr_provider])

        media = scanner.scan(media_path=self.image_path, tools=["tags", "nsfw", "ocr"])

        self.assertIsInstance(media, LizMedia)
        self.assertEqual(media.path, self.image_path.resolve())
        self.assertEqual(media.ai_tags, ["cat", "indoor"])
        self.assertFalse(media.ai_nsfw)
        self.assertEqual(media.ai_ocr_text, ["HELLO"])
        self.assertTrue(media.ai_has_ocr_text)
        self.assertTrue(media.ai_scanned)
        self.assertEqual(media.ai_file_name, "sample.png")
        self.assertEqual(tags_provider.calls, 1)
        self.assertEqual(nsfw_provider.calls, 1)
        self.assertEqual(ocr_provider.calls, 1)

    def test_scan_from_base64_creates_media_and_preserves_payload(self):
        payload = base64.b64encode(self.image_path.read_bytes()).decode("utf-8")
        tags_provider = _StaticProvider(AiScanTool.TAGS, AiScanResult(tags=["poster"]))
        scanner = AiMediaScanner(providers=[tags_provider])

        media = scanner.scan(base64_content=payload, file_name="from_base64.png", tools=["TAGS"])
        try:
            self.assertIsInstance(media, LizMedia)
            self.assertEqual(media.ai_tags, ["poster"])
            self.assertEqual(media.base64_content, payload)
            self.assertEqual(media.file_name, media.path.name)
            self.assertTrue(media.path.exists())
            self.assertEqual(media.path.suffix, ".png")
        finally:
            media.path.unlink(missing_ok=True)

    def test_scan_accepts_data_uri_without_filename(self):
        payload = base64.b64encode(self.image_path.read_bytes()).decode("utf-8")
        data_uri = f"data:image/png;base64,{payload}"
        ocr_provider = _StaticProvider(AiScanTool.OCR, AiScanResult(ocr_text=[], ocr_detected=False))
        scanner = AiMediaScanner(providers=[ocr_provider])

        media = scanner.scan(base64_content=data_uri, tools=["ocr"])
        try:
            self.assertEqual(media.path.suffix, ".png")
            self.assertFalse(media.ai_has_ocr_text)
            self.assertEqual(media.ai_ocr_text, [])
            self.assertTrue(media.ai_scanned)
        finally:
            media.path.unlink(missing_ok=True)

    def test_duplicate_aliases_are_normalized_once(self):
        tags_provider = _StaticProvider(AiScanTool.TAGS, AiScanResult(tags=["one"]))
        scanner = AiMediaScanner(providers=[tags_provider])

        media = scanner.scan(media_path=self.image_path, tools=["tag-joytag", "JOYTAG", "tags"])

        self.assertEqual(media.ai_tags, ["one"])
        self.assertEqual(tags_provider.calls, 1)

    def test_scan_requires_supported_tools(self):
        scanner = AiMediaScanner(providers=[])
        with self.assertRaises(ValueError):
            scanner.scan(media_path=self.image_path, tools=["something-else"])

    def test_scan_requires_one_source(self):
        scanner = AiMediaScanner(providers=[])
        with self.assertRaises(ValueError):
            scanner.scan(tools=["OCR"])

    def test_temporary_file_is_deleted_on_failure(self):
        payload = base64.b64encode(self.image_path.read_bytes()).decode("utf-8")
        scanner = AiMediaScanner(providers=[_FailingProvider()])

        before = {path for path in Path(tempfile.gettempdir()).glob("pyliz_media_*")}
        with self.assertRaises(RuntimeError):
            scanner.scan(base64_content=payload, file_name="failure.png", tools=["TAGS"])
        after = {path for path in Path(tempfile.gettempdir()).glob("pyliz_media_*")}

        self.assertEqual(before, after)

    def test_scan_all_tools_across_all_input_types(self):
        """Tests 3 tools (TAGS, NSFW, OCR) across 3 input types (Path, Raw Base64, Data URI)."""
        tags_res = AiScanResult(tags=["tag1"])
        nsfw_res = AiScanResult(nsfw=True)
        ocr_res = AiScanResult(ocr_text=["text1"], ocr_detected=True)

        providers = [
            _StaticProvider(AiScanTool.TAGS, tags_res),
            _StaticProvider(AiScanTool.NSFW, nsfw_res),
            _StaticProvider(AiScanTool.OCR, ocr_res),
        ]
        scanner = AiMediaScanner(providers=providers)
        tools = ["tags", "nsfw", "ocr"]

        # 1. Local Path
        media_path = scanner.scan(media_path=self.image_path, tools=tools)
        self.assertEqual(media_path.ai_tags, ["tag1"])
        self.assertTrue(media_path.ai_nsfw)
        self.assertEqual(media_path.ai_ocr_text, ["text1"])

        # 2. Raw Base64
        raw_b64 = base64.b64encode(self.image_path.read_bytes()).decode("utf-8")
        media_b64 = scanner.scan(base64_content=raw_b64, file_name="test.png", tools=tools)
        try:
            self.assertEqual(media_b64.ai_tags, ["tag1"])
            self.assertTrue(media_b64.ai_nsfw)
            self.assertEqual(media_b64.ai_ocr_text, ["text1"])
            self.assertEqual(media_b64.ai_file_name, "test.png")
        finally:
            media_b64.path.unlink(missing_ok=True)

        # 3. Data URI
        data_uri = f"data:image/png;base64,{raw_b64}"
        media_uri = scanner.scan(base64_content=data_uri, tools=tools)
        try:
            self.assertEqual(media_uri.ai_tags, ["tag1"])
            self.assertTrue(media_uri.ai_nsfw)
            self.assertEqual(media_uri.ai_ocr_text, ["text1"])
            self.assertTrue(media_uri.path.suffix == ".png")
        finally:
            media_uri.path.unlink(missing_ok=True)

    def test_scan_video_input(self):
        """Tests that AiMediaScanner correctly identifies and processes video files."""
        video_path = Path(self.temp_dir.name) / "test.mp4"
        video_path.write_bytes(b"fake video content")

        tags_provider = _StaticProvider(AiScanTool.TAGS, AiScanResult(tags=["motion"]))
        scanner = AiMediaScanner(providers=[tags_provider])

        media = scanner.scan(media_path=video_path, tools=["tags"])
        self.assertTrue(media.is_video)
        self.assertEqual(media.ai_tags, ["motion"])
        self.assertEqual(media.ai_file_name, "test.mp4")


if __name__ == "__main__":
    unittest.main()

