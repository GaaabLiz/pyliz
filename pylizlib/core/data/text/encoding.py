"""Conservative BOM/UTF/Windows-1252 detection for bounded text scans."""

import codecs
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class EncodingDecision:
    """Record the encoding decision without changing the detector's legacy policy.

    Attributes:
        encoding (str): Codec name to use for streaming text decoding.
        binary (bool): Whether automatic detection identified obvious binary content.
        used_fallback (bool): Whether UTF-8 sample decoding required Windows-1252.
    """

    encoding: str
    binary: bool
    used_fallback: bool


class EncodingDetector:
    """Inspect a bounded byte sample without reading the entire file."""

    def __init__(self, sample_bytes: int = 8 * 1024):
        """Choose the detection sample limit in bytes.

        Args:
            sample_bytes (int): Maximum bytes read for detection, default 8192.

        Returns:
            None: Detection performs I/O only when detect is called.
        """
        self._DETECTION_SAMPLE_BYTES = sample_bytes

    def detect(self, file_path: Path, preferred_encoding: str | None) -> EncodingDecision:
        """Choose BOM/UTF/Windows-1252 decoding and classify obvious binary data.

        Args:
            file_path (Path): File from which at most sample_bytes bytes are read.
            preferred_encoding (str | None): Explicit codec bypassing automatic
                detection and binary checks. The sample is still read first.

        Returns:
            EncodingDecision: Chosen codec, binary classification and whether the
            sample required Windows-1252 fallback. No full-file validity is implied.

        Raises:
            OSError: If opening or reading the sample fails.
            ValueError: If an automatically selected codec cannot be looked up.
        """
        with file_path.open("rb") as file_stream:
            sample = file_stream.read(self._DETECTION_SAMPLE_BYTES)

        if preferred_encoding:
            return EncodingDecision(preferred_encoding, False, False)
        if sample.startswith(codecs.BOM_UTF32_LE):
            encoding = "utf-32"
        elif sample.startswith(codecs.BOM_UTF32_BE):
            encoding = "utf-32"
        elif sample.startswith(codecs.BOM_UTF8):
            encoding = "utf-8-sig"
        elif sample.startswith(codecs.BOM_UTF16_LE) or sample.startswith(codecs.BOM_UTF16_BE):
            encoding = "utf-16"
        else:
            encoding = self.detect_bomless_utf16(sample) or ""
            if not encoding:
                try:
                    codecs.getincrementaldecoder("utf-8")().decode(
                        sample,
                        final=len(sample) < self._DETECTION_SAMPLE_BYTES,
                    )
                    encoding = "utf-8"
                except UnicodeDecodeError:
                    encoding = "cp1252"
                    text = sample.decode(encoding, errors="replace")
                    if self.looks_binary(sample, text):
                        return EncodingDecision(encoding, True, True)
                    return EncodingDecision(encoding, False, True)

        try:
            codecs.lookup(encoding)
        except LookupError:
            raise ValueError(f"Unknown text encoding: {encoding}")
        if self.looks_binary(
            sample,
            sample.decode(encoding, errors="replace"),
            allow_nul=encoding.startswith(("utf-16", "utf-32")),
        ):
            return EncodingDecision(encoding, True, False)
        return EncodingDecision(encoding, False, False)

    @staticmethod
    def detect_bomless_utf16(sample: bytes) -> str | None:
        """Recognize ASCII-heavy UTF-16 using alternating NUL-byte counts.

        Args:
            sample (bytes): Bounded raw sample; an unmatched trailing byte is ignored.

        Returns:
            str | None: utf-16-le or utf-16-be when the existing threshold matches,
            otherwise None. Samples shorter than four byte pairs are inconclusive.
        """
        pairs = len(sample) // 2
        if pairs < 4:
            return None
        even_nuls = sum(byte == 0 for byte in sample[: pairs * 2 : 2])
        odd_nuls = sum(byte == 0 for byte in sample[1 : pairs * 2 : 2])
        threshold = max(3, pairs // 4)
        if odd_nuls >= threshold and even_nuls <= pairs // 20:
            return "utf-16-le"
        if even_nuls >= threshold and odd_nuls <= pairs // 20:
            return "utf-16-be"
        return None

    @staticmethod
    def looks_binary(sample: bytes, decoded: str, allow_nul: bool = False) -> bool:
        """Classify NUL-containing or predominantly non-printable samples as binary.

        Args:
            sample (bytes): Original bounded bytes, used for NUL checks.
            decoded (str): Sample decoded with replacement for undecodable bytes.
            allow_nul (bool): Permit NUL bytes when a UTF-16/32 codec was selected.

        Returns:
            bool: True for a forbidden NUL or a printable-character ratio below 0.65;
            empty bytes/text are not considered binary by this heuristic.
        """
        if not sample:
            return False
        if b"\x00" in sample and not allow_nul:
            return True
        if not decoded:
            return False
        printable = sum(character.isprintable() or character in "\r\n\t\f" for character in decoded)
        return printable / len(decoded) < 0.65
