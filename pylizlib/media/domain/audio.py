from dataclasses import dataclass


@dataclass
class AudioSegment:
    """
    Data container for a transcribed segment of audio.
    Includes text content, timing bounds, and speech recognition confidence.
    """

    text: str
    start_time: float
    end_time: float
    confidence: float = 0.0
