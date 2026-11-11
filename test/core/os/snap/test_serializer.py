"""
Unit tests for pylizlib.core.os.snap.serializer

Covers:
    - SnapshotSerializer.to_json / from_json round-trip
    - Correct handling of all optional datetime fields (None → preserved None)
    - BUG-3 regression: date_last_used survives serialisation
    - update_field for string, datetime, dict and list values
    - JSON file written with UTF-8 encoding
    - _converter raises TypeError for unsupported types
"""

import json
import unittest
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from unittest.mock import patch

from pylizlib.core.os.snap.domain import SnapDirAssociation, Snapshot
from pylizlib.core.os.snap.serializer import SnapshotSerializer
from test.core.os.snap.conftest import (
    SOURCE_DATA_PATH,
    TEST_LOCAL_ROOT,
    create_source_dirs,
    make_snapshot,
    setup_test_dirs,
    teardown_test_dirs,
)


class TestSnapshotSerializerRoundTrip(unittest.TestCase):
    """Round-trip serialisation tests."""

    def setUp(self):
        setup_test_dirs()
        create_source_dirs(SOURCE_DATA_PATH, ["ser1", "ser2"])

    def tearDown(self):
        teardown_test_dirs()

    def test_full_round_trip(self):
        src = list(SOURCE_DATA_PATH.iterdir())
        snap = make_snapshot("SerSnap", src, n=2)
        snap.add_data_item("k", "v")
        snap.tags = ["alpha", "beta"]
        snap.date_modified = datetime.now()
        snap.directories[0].integrity_manifest = {
            ".": {"type": "directory", "size": 0, "sha256": None},
            "file.txt": {"type": "file", "size": 3, "sha256": "a" * 64},
        }

        json_path = TEST_LOCAL_ROOT / "ser_snap.json"
        SnapshotSerializer.to_json(snap, json_path)
        loaded = SnapshotSerializer.from_json(json_path)

        self.assertEqual(loaded.id, snap.id)
        self.assertEqual(loaded.name, snap.name)
        self.assertEqual(loaded.tags, snap.tags)
        self.assertEqual(loaded.data, snap.data)
        self.assertEqual(len(loaded.directories), len(snap.directories))
        self.assertEqual(loaded.directories[0].integrity_manifest, snap.directories[0].integrity_manifest)
        self.assertEqual(loaded.directories[0].mb_size, 3 / (1024 * 1024))
        self.assertEqual(loaded.directories[0].directory_name, snap.directories[0].directory_name)
        self.assertIsNotNone(loaded.date_modified)

    def test_legacy_metadata_retains_its_index_based_storage_name(self):
        json_path = TEST_LOCAL_ROOT / "legacy_storage_name.json"
        json_path.write_text(
            json.dumps(
                {
                    "id": "LegacyStorage",
                    "name": "Legacy storage",
                    "desc": "",
                    "directories": [{"index": 1, "original_path": "/source/data", "folder_id": "legacy-id", "mb_size": 0}],
                }
            ),
            encoding="utf-8",
        )

        loaded = SnapshotSerializer.from_json(json_path)
        self.assertEqual(loaded.directories[0].directory_name, "1-data")
        loaded.directories[0].index = 7

        SnapshotSerializer.to_json(loaded, json_path)
        raw = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(raw["directories"][0]["storage_name"], "1-data")
        self.assertEqual(SnapshotSerializer.from_json(json_path).directories[0].directory_name, "1-data")

    def test_optional_datetime_fields_survive_as_none(self):
        src = list(SOURCE_DATA_PATH.iterdir())
        snap = make_snapshot("NullDates", src, n=1)
        json_path = TEST_LOCAL_ROOT / "null_dates.json"
        SnapshotSerializer.to_json(snap, json_path)
        loaded = SnapshotSerializer.from_json(json_path)
        self.assertIsNone(loaded.date_modified)
        self.assertIsNone(loaded.date_last_used)
        self.assertIsNone(loaded.date_last_modified)
        self.assertIsNone(loaded.capture_started_at)
        self.assertIsNone(loaded.capture_completed_at)

    def test_capture_timestamps_round_trip_as_timezone_aware_values(self):
        source = list(SOURCE_DATA_PATH.iterdir())
        snapshot = make_snapshot("CaptureTimes", source, n=1)
        snapshot.capture_started_at = datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc)
        snapshot.capture_completed_at = datetime(2026, 11, 12, 10, 1, tzinfo=timezone.utc)
        json_path = TEST_LOCAL_ROOT / "capture_times.json"

        SnapshotSerializer.to_json(snapshot, json_path)
        loaded = SnapshotSerializer.from_json(json_path)

        self.assertEqual(loaded.capture_started_at, snapshot.capture_started_at)
        self.assertEqual(loaded.capture_completed_at, snapshot.capture_completed_at)
        raw = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertTrue(raw["capture_started_at"].endswith("+00:00"))

    def test_legacy_missing_size_does_not_scan_original_path(self):
        json_path = TEST_LOCAL_ROOT / "legacy_missing_size.json"
        json_path.write_text(
            json.dumps(
                {
                    "id": "LegacyNoSize",
                    "name": "Legacy without size",
                    "desc": "",
                    "directories": [{"index": 1, "original_path": "/remote/share/data", "folder_id": "remote"}],
                }
            ),
            encoding="utf-8",
        )

        with patch("os.walk", side_effect=AssertionError("source tree was scanned")) as walk:
            loaded = SnapshotSerializer.from_json(json_path)

        walk.assert_not_called()
        self.assertIsNone(loaded.directories[0].mb_size)

    def test_bug3_date_last_used_survives_round_trip(self):
        """BUG-3: date_last_used must be preserved across JSON serialisation."""
        src = list(SOURCE_DATA_PATH.iterdir())
        snap = make_snapshot("Bug3Snap", src, n=1)
        snap.date_last_used = datetime(2025, 6, 15, 12, 0, 0)

        json_path = TEST_LOCAL_ROOT / "bug3.json"
        SnapshotSerializer.to_json(snap, json_path)
        loaded = SnapshotSerializer.from_json(json_path)

        self.assertIsNotNone(loaded.date_last_used)
        self.assertEqual(loaded.date_last_used, snap.date_last_used)

    def test_json_file_is_valid_utf8(self):
        src = list(SOURCE_DATA_PATH.iterdir())
        snap = make_snapshot("Utf8Snap", src, n=1)
        snap.desc = "Descrizione con caratteri speciali: àèìòù €"
        json_path = TEST_LOCAL_ROOT / "utf8.json"
        SnapshotSerializer.to_json(snap, json_path)
        content = json_path.read_text(encoding="utf-8")
        self.assertIn("Descrizione", content)

    def test_directories_deserialised_as_snap_dir_association(self):
        src = list(SOURCE_DATA_PATH.iterdir())
        snap = make_snapshot("DirDeser", src, n=2)
        json_path = TEST_LOCAL_ROOT / "dir_deser.json"
        SnapshotSerializer.to_json(snap, json_path)
        loaded = SnapshotSerializer.from_json(json_path)
        self.assertTrue(all(isinstance(d, SnapDirAssociation) for d in loaded.directories))

    def test_json_rejects_string_index_that_could_traverse_outside_snapshot(self):
        json_path = TEST_LOCAL_ROOT / "bad_index.json"
        json_path.write_text(
            json.dumps(
                {
                    "id": "invalid-index",
                    "name": "Invalid",
                    "desc": "",
                    "directories": [{"index": "../../escape", "original_path": "/source", "folder_id": "assoc"}],
                }
            ),
            encoding="utf-8",
        )

        with self.assertRaises(TypeError):
            SnapshotSerializer.from_json(json_path)

    def test_json_rejects_relative_original_path(self):
        json_path = TEST_LOCAL_ROOT / "relative_original_path.json"
        json_path.write_text(
            json.dumps(
                {
                    "id": "relative-path",
                    "name": "Relative path",
                    "desc": "",
                    "directories": [{"index": 1, "original_path": "data", "folder_id": "assoc"}],
                }
            ),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "relative paths cannot be resolved safely"):
            SnapshotSerializer.from_json(json_path)


class TestSnapshotSerializerSymlinkSafety(unittest.TestCase):
    def setUp(self):
        setup_test_dirs()

    def tearDown(self):
        teardown_test_dirs()

    def test_update_field_does_not_follow_a_metadata_symlink(self):
        external_json = TEST_LOCAL_ROOT / "outside.json"
        external_json.write_text('{"name": "outside"}', encoding="utf-8")
        linked_json = TEST_LOCAL_ROOT / "linked.json"
        try:
            linked_json.symlink_to(external_json)
        except (NotImplementedError, OSError) as error:
            self.skipTest(f"symlink creation is unavailable: {error}")

        with self.assertRaises((OSError, ValueError)):
            SnapshotSerializer.update_field(linked_json, "name", "changed")

        self.assertEqual(external_json.read_text(encoding="utf-8"), '{"name": "outside"}')


class TestSnapshotSerializerUpdateField(unittest.TestCase):
    """Tests for SnapshotSerializer.update_field partial-write API."""

    def setUp(self):
        setup_test_dirs()
        create_source_dirs(SOURCE_DATA_PATH, ["upd1"])

    def tearDown(self):
        teardown_test_dirs()

    def _make_json(self, filename: str) -> tuple[Snapshot, Path]:
        src = list(SOURCE_DATA_PATH.iterdir())
        snap = make_snapshot("UpdSnap", src, n=1)
        json_path = TEST_LOCAL_ROOT / filename
        SnapshotSerializer.to_json(snap, json_path)
        return snap, json_path

    def test_update_string_field(self):
        snap, json_path = self._make_json("upd_str.json")
        SnapshotSerializer.update_field(json_path, "name", "Updated Name")
        loaded = SnapshotSerializer.from_json(json_path)
        self.assertEqual(loaded.name, "Updated Name")

    def test_update_datetime_field_as_isoformat(self):
        snap, json_path = self._make_json("upd_dt.json")
        new_ts = datetime(2026, 1, 1, 0, 0, 0)
        SnapshotSerializer.update_field(json_path, "date_last_used", new_ts.isoformat())
        loaded = SnapshotSerializer.from_json(json_path)
        self.assertEqual(loaded.date_last_used, new_ts)

    def test_update_dict_field(self):
        snap, json_path = self._make_json("upd_dict.json")
        SnapshotSerializer.update_field(json_path, "data", {"env": "production"})
        loaded = SnapshotSerializer.from_json(json_path)
        self.assertEqual(loaded.data.get("env"), "production")

    def test_update_list_field(self):
        snap, json_path = self._make_json("upd_list.json")
        SnapshotSerializer.update_field(json_path, "tags", ["new_tag"])
        loaded = SnapshotSerializer.from_json(json_path)
        self.assertEqual(loaded.tags, ["new_tag"])

    def test_update_field_preserves_other_fields(self):
        snap, json_path = self._make_json("upd_preserve.json")
        original_desc = snap.desc
        SnapshotSerializer.update_field(json_path, "name", "Changed")
        loaded = SnapshotSerializer.from_json(json_path)
        self.assertEqual(loaded.desc, original_desc)

    def test_update_field_to_null(self):
        snap, json_path = self._make_json("upd_null.json")
        SnapshotSerializer.update_field(json_path, "date_modified", None)
        data = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertIsNone(data["date_modified"])


class TestSnapshotSerializerConverter(unittest.TestCase):
    """Tests for the internal JSON type converter."""

    def test_converter_raises_for_unsupported_type(self):
        with self.assertRaises(TypeError):
            SnapshotSerializer._converter(object())

    def test_converter_handles_datetime(self):
        dt = datetime(2026, 5, 31, 12, 0, 0)
        result = SnapshotSerializer._converter(dt)
        self.assertIsInstance(result, str)
        self.assertIn("2026", result)

    def test_converter_handles_enum(self):
        class DummyEnum(Enum):
            FOO = "bar"

        result = SnapshotSerializer._converter(DummyEnum.FOO)
        self.assertEqual(result, "bar")


if __name__ == "__main__":
    unittest.main()
