import os
import unittest
import shutil
import json
from pathlib import Path
from dataclasses import asdict
from typing import List

from dotenv import load_dotenv

from pylizlib.eaglecool.reader import EagleCoolReader, EagleItem
from pylizlib.eaglecool.model.metadata import Metadata
from pylizlib.core.domain.os import FileType

# Load environment variables
load_dotenv()


class TestEagleCoolReader(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment using a temporary directory."""
        # Always use a local temporary directory for unit tests to ensure isolation
        cls.test_eagle_dir = "test_data_temp_eagle_library"
        cls.library_path = Path(cls.test_eagle_dir)
        cls.images_dir = cls.library_path / "images"

        # Ensure clean start
        if cls.library_path.exists():
            shutil.rmtree(cls.library_path)

        cls.create_mock_library()

    @classmethod
    def tearDownClass(cls):
        """Clean up after all tests."""
        if cls.library_path.exists():
            shutil.rmtree(cls.library_path)

    @classmethod
    def create_mock_library(cls):
        """Creates a mock Eagle library structure for testing."""
        cls.images_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. Standard valid item
        cls.create_mock_item(
            "item1.info", 
            "image1.jpg", 
            {"id": "item1", "name": "Test Image", "tags": ["art", "design"], "isDeleted": False}
        )

        # 2. Deleted item
        cls.create_mock_item(
            "item2.info", 
            "image2.png", 
            {"id": "item2", "name": "Deleted Image", "tags": ["trash"], "isDeleted": True}
        )

        # 3. Item with specific tag
        cls.create_mock_item(
            "item3.info", 
            "image3.jpg", 
            {"id": "item3", "name": "Tagged Image", "tags": ["special"], "isDeleted": False}
        )

        # 4. Item missing media file
        cls.create_mock_item(
            "item4.info", 
            None, 
            {"id": "item4", "name": "Missing Media", "tags": [], "isDeleted": False}
        )

        # 5. Item missing metadata
        folder = cls.images_dir / "item5.info"
        folder.mkdir()
        (folder / "image5.jpg").touch()

        # 6. Invalid file type (text file)
        cls.create_mock_item(
            "item6.info", 
            "note.txt", 
            {"id": "item6", "name": "Text Note", "tags": [], "isDeleted": False}
        )
        
        # 7. Metadata parse error
        folder = cls.images_dir / "item7.info"
        folder.mkdir()
        (folder / "image7.jpg").touch()
        with open(folder / "metadata.json", "w") as f:
            f.write("{invalid_json}")


    @classmethod
    def create_mock_item(cls, folder_name: str, media_name: str | None, metadata: dict):
        folder = cls.images_dir / folder_name
        folder.mkdir(exist_ok=True)
        
        if media_name:
            (folder / media_name).touch()
            
        if metadata:
            with open(folder / "metadata.json", "w") as f:
                json.dump(metadata, f)

    def setUp(self):
        """Reset reader before each test."""
        pass

    def test_initialization(self):
        """Test that the reader initializes correctly."""
        reader = EagleCoolReader(self.library_path)
        self.assertEqual(reader.catalogue, self.library_path)
        self.assertFalse(reader.include_deleted)
        self.assertIsNone(reader.filter_tags)

    def test_run_standard_scan(self):
        """Test a basic scan of the library."""
        reader = EagleCoolReader(self.library_path)
        reader.run()
        
        # item1 and item3 should be found (valid, non-deleted, media file exists)
        # item2 is deleted
        # item4 is missing media
        # item5 is missing metadata
        # item6 is invalid type
        # item7 has corrupt metadata
        
        found_ids = [item.metadata.id for item in reader.items]
        self.assertIn("item1", found_ids)
        self.assertIn("item3", found_ids)
        self.assertNotIn("item2", found_ids)
        
        # Verify specific attributes of a loaded item
        item1 = next(i for i in reader.items if i.metadata.id == "item1")
        self.assertEqual(item1.metadata.name, "Test Image")
        self.assertTrue(str(item1.file_path).endswith("image1.jpg"))

    def test_include_deleted(self):
        """Test scanning with include_deleted=True."""
        reader = EagleCoolReader(self.library_path, include_deleted=True)
        reader.run()
        
        found_ids = [item.metadata.id for item in reader.items]
        self.assertIn("item1", found_ids)
        self.assertIn("item2", found_ids) # Should be present now
        self.assertIn("item3", found_ids)

    def test_filter_tags(self):
        """Test scanning with tag filtering."""
        reader = EagleCoolReader(self.library_path, filter_tags=["special"])
        reader.run()
        
        found_ids = [item.metadata.id for item in reader.items]
        self.assertIn("item3", found_ids) # Has 'special' tag
        self.assertNotIn("item1", found_ids) # Does not have 'special' tag

        # Verify skipped items count/reason
        skipped_item1 = next((i for i, r in reader.items_skipped if i.metadata.id == "item1"), None)
        self.assertIsNotNone(skipped_item1)
        # Check reason string roughly (implementation detail dependent)
        reason = next(r for i, r in reader.items_skipped if i.metadata.id == "item1")
        self.assertIn("Tag mismatch", reason)

    def test_missing_metadata_error(self):
        """Test handling of folders missing metadata.json."""
        reader = EagleCoolReader(self.library_path)
        reader.run()
        
        # item5.info has media but no metadata
        # Expecting an entry in error_paths
        error_entry = next((path for path, reason in reader.error_paths if "item5.info" in str(path)), None)
        self.assertIsNotNone(error_entry)
        
        reason = next((r for p, r in reader.error_paths if "item5.info" in str(p)), "")
        self.assertIn("Missing metadata.json", reason)

    def test_missing_media_file_error(self):
        """Test handling of folders missing the media file."""
        reader = EagleCoolReader(self.library_path)
        reader.run()
        
        # item4.info has metadata but no media
        error_entry = next((path for path, reason in reader.error_paths if "item4.info" in str(path)), None)
        self.assertIsNotNone(error_entry)
        
        reason = next((r for p, r in reader.error_paths if "item4.info" in str(p)), "")
        self.assertIn("Missing media file", reason)

    def test_invalid_metadata_json(self):
        """Test handling of corrupt metadata.json."""
        reader = EagleCoolReader(self.library_path)
        reader.run()
        
        # item7.info has invalid json
        error_entry = next((path for path, reason in reader.error_paths if "item7.info" in str(path)), None)
        self.assertIsNotNone(error_entry)
        
        reason = next((r for p, r in reader.error_paths if "item7.info" in str(p)), "")
        self.assertIn("Error reading metadata", reason)

    def test_unsupported_file_type(self):
        """Test that non-media files are skipped."""
        reader = EagleCoolReader(self.library_path)
        reader.run()

        # item6.info is a text file
        found_ids = [item.metadata.id for item in reader.items]
        self.assertNotIn("item6", found_ids)
        
        skipped = next((i for i, r in reader.items_skipped if i.metadata.id == "item6"), None)
        self.assertIsNotNone(skipped)
        reason = next(r for i, r in reader.items_skipped if i.metadata.id == "item6")
        self.assertIn("Unsupported file type", reason)

    def test_invalid_catalogue_path(self):
        """Test that initialization with an invalid path raises or handles error."""
        invalid_path = Path("/path/that/does/not/exist")
        reader = EagleCoolReader(invalid_path)
        
        with self.assertRaises(ValueError):
            reader.run()


if __name__ == '__main__':
    unittest.main()
