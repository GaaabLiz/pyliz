
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from pylizlib.media.lizmedia import LizMedia, LizMediaSearchResult, MediaListResult, MediaStatus
from pylizlib.media.script.organizer.searcher import MediaSearcher

class TestXMPCollision(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp(prefix="pyliz_xmp_test_"))
        self.source_dir = self.test_dir / "source"
        self.source_dir.mkdir()
        
        # Create two different directories with a file of the same name
        self.dir1 = self.source_dir / "dir1"
        self.dir1.mkdir()
        self.file1 = self.dir1 / "image.mp4"
        self.file1.write_text("content1")
        
        self.dir2 = self.source_dir / "dir2"
        self.dir2.mkdir()
        self.file2 = self.dir2 / "image.mp4"
        self.file2.write_text("content2")

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    @patch("pylizlib.media.util.metadata.MetadataHandler.generate_xmp")
    def test_generate_xmps_no_collision(self, mock_generate_xmp):
        # Setup mock to succeed
        mock_generate_xmp.return_value = True
        
        # Mock LizMedia objects
        media1 = MagicMock(spec=LizMedia)
        media1.path = self.file1
        media1.file_name = "image.mp4"
        media1.has_xmp_sidecar.return_value = False
        media1.eagle_metadata = None
        
        media2 = MagicMock(spec=LizMedia)
        media2.path = self.file2
        media2.file_name = "image.mp4"
        media2.has_xmp_sidecar.return_value = False
        media2.eagle_metadata = None
        
        # Search results
        res1 = LizMediaSearchResult(status=MediaStatus.ACCEPTED, path=self.file1, media=media1)
        res2 = LizMediaSearchResult(status=MediaStatus.ACCEPTED, path=self.file2, media=media2)
        
        searcher = MediaSearcher(str(self.source_dir))
        searcher._result.accepted = [res1, res2]
        
        # This should not raise an error now
        searcher.generate_missing_xmps()
        
        # Verify that two different paths were used
        self.assertEqual(mock_generate_xmp.call_count, 2)
        call_args = mock_generate_xmp.call_args_list
        path1 = call_args[0][0][0]
        path2 = call_args[1][0][0]
        
        self.assertNotEqual(path1, path2)
        self.assertTrue("image.xmp" in str(path1))
        self.assertTrue("image.xmp" in str(path2))
        
        # Cleanup
        searcher.cleanup_generated_xmps()

if __name__ == "__main__":
    unittest.main()
