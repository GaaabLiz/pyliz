"""Versioned journal codecs retain the exact legacy acceptance boundary."""

import json

import pytest

from pylizlib.core.os.snap.storage.recovery.models import JournalCodec
from pylizlib.core.os.snap.storage.transactions import TransactionRecoveryError


def test_codec_preserves_unknown_fields_and_legacy_version_equality(tmp_path):
    """Typing does not introduce stricter validation or drop future payload fields."""
    payload = {"version": True, "scope_root": tmp_path.as_posix(), "operation": "future", "state": "prepared", "payload": {"unknown": [1, 2]}, "future": 10}
    assert JournalCodec.validate(payload, tmp_path) is None
    assert json.loads(JournalCodec.encode(payload)) == payload
    assert JournalCodec.encode(payload) == json.dumps(payload, indent=2)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"version": 2, "state": "unknown"}, "Unsupported snapshot transaction journal version"),
        ({"scope_root": "other", "operation": 1}, "belongs to another storage scope"),
        ({"operation": 1}, "operation must be a string"),
        ({"state": "unknown"}, "invalid state"),
        ({"payload": []}, "payload must be an object"),
    ],
)
def test_codec_retains_validation_order(tmp_path, changes, message):
    """Malformed fields keep their prior error category and first reported failure."""
    payload = {"version": 1, "scope_root": tmp_path.as_posix(), "operation": "edit", "state": "prepared", "payload": {}}
    payload.update(changes)
    with pytest.raises(TransactionRecoveryError, match=message):
        JournalCodec.validate(payload, tmp_path)
