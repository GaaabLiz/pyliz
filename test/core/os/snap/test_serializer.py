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
from datetime import datetime
from pathlib import Path

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

        json_path = TEST_LOCAL_ROOT / "ser_snap.json"
        SnapshotSerializer.to_json(snap, json_path)
        loaded = SnapshotSerializer.from_json(json_path)

        self.assertEqual(loaded.id, snap.id)
        self.assertEqual(loaded.name, snap.name)
        self.assertEqual(loaded.tags, snap.tags)
        self.assertEqual(loaded.data, snap.data)
        self.assertEqual(len(loaded.directories), len(snap.directories))
        self.assertIsNotNone(loaded.date_modified)

    def test_optional_datetime_fields_survive_as_none(self):
        src = list(SOURCE_DATA_PATH.iterdir())
        snap = make_snapshot("NullDates", src, n=1)
        json_path = TEST_LOCAL_ROOT / "null_dates.json"
        SnapshotSerializer.to_json(snap, json_path)
        loaded = SnapshotSerializer.from_json(json_path)
        self.assertIsNone(loaded.date_modified)
        self.assertIsNone(loaded.date_last_used)
        self.assertIsNone(loaded.date_last_modified)

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


if __name__ == "__main__":
    unittest.main()
