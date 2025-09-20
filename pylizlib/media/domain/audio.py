from dataclasses import dataclass


@dataclass
class AudioSegment:
    """Represents a transcribed segment of audio with timing information"""
    text: str
    start_time: float
    end_time: float
    confidence: float = 0.0