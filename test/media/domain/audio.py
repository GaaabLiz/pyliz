import unittest

from pylizlib.media.domain.ai import AiPayloadMediaInfo
from pylizlib.media.domain.audio import AudioSegment


class AudioDomainTestCase(unittest.TestCase):
    def test_audio_segment_dataclass(self):
        seg = AudioSegment(text="hello", start_time=0.5, end_time=2.0, confidence=0.95)
        self.assertEqual(seg.text, "hello")
        self.assertEqual(seg.start_time, 0.5)
        self.assertEqual(seg.end_time, 2.0)
        self.assertEqual(seg.confidence, 0.95)

    def test_ai_payload_media_info_import(self):
        self.assertIsNotNone(AiPayloadMediaInfo)


if __name__ == "__main__":
    unittest.main()
