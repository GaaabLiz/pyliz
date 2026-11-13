import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from pylizlib.media.lizmedia import (
    LizMedia,
    LizMediaSearchResult,
    MediaListResult,
    MediaStatus,
)
from pylizlib.media.view.table import MediaListResultPrinter


class MediaListResultPrinterTestCase(unittest.TestCase):
    def setUp(self):
        self.result = MediaListResult()

    def test_print_empty_lists(self):
        printer = MediaListResultPrinter(self.result)
        with patch.object(printer._console, "print") as mock_print:
            printer.print_accepted()
            mock_print.assert_called_once()
            self.assertIn("No accepted", str(mock_print.call_args))

        with patch.object(printer._console, "print") as mock_print:
            printer.print_rejected()
            mock_print.assert_called_once()
            self.assertIn("No media files were rejected", str(mock_print.call_args))

        with patch.object(printer._console, "print") as mock_print:
            printer.print_errored()
            mock_print.assert_called_once()
            self.assertIn("No media files were errored", str(mock_print.call_args))

    def test_print_tables_with_media_and_sorting(self):
        # Create dummy LizMedia instances
        mock_media1 = MagicMock(spec=LizMedia)
        mock_media1.file_name = "b_image.jpg"
        mock_media1.extension = ".jpg"
        mock_media1.creation_date_from_exif_or_file_or_sidecar = datetime(2023, 2, 1)
        mock_media1.has_exif_data = True
        mock_media1.size_mb = 2.5
        mock_media1.attached_sidecar_files = [Path("b_image.xmp")]

        mock_media2 = MagicMock(spec=LizMedia)
        mock_media2.file_name = "a_image.png"
        mock_media2.extension = ".png"
        mock_media2.creation_date_from_exif_or_file_or_sidecar = datetime(2023, 1, 1)
        mock_media2.has_exif_data = False
        mock_media2.size_mb = 1.0
        mock_media2.attached_sidecar_files = []

        item1 = LizMediaSearchResult(status=MediaStatus.ACCEPTED, path=Path("/b.jpg"), media=mock_media1)
        item2 = LizMediaSearchResult(status=MediaStatus.ACCEPTED, path=Path("/a.png"), media=mock_media2)
        # Item without media
        item3 = LizMediaSearchResult(status=MediaStatus.REJECTED, path=Path("/c.mp4"), reason="Too large")

        self.result.accepted = [item1, item2]
        self.result.rejected = [item3]
        self.result.errored = [item3]

        printer = MediaListResultPrinter(self.result)

        # Test accepted table printing and sort indices 0 through 6
        for sort_idx in range(7):
            with patch.object(printer._console, "print") as mock_print:
                printer.print_accepted(sort_index=sort_idx)
                mock_print.assert_called_once()

        # Test rejected and errored tables
        with patch.object(printer._console, "print") as mock_print:
            printer.print_rejected(sort_index=1)
            mock_print.assert_called_once()

        with patch.object(printer._console, "print") as mock_print:
            printer.print_errored(sort_index=6)
            mock_print.assert_called_once()


if __name__ == "__main__":
    unittest.main()
