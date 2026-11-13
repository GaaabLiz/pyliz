"""Shared manifest decoding keeps each format's validation and path policy."""

import os

import pytest

from pylizlib.core.os.snap.operations.backup.associations import LEGACY_ASSOCIATIONS, MODERN_ASSOCIATIONS, parse_associations
from pylizlib.core.os.snap.operations.backup_manifest import BACKUP_MANIFEST_NAME


@pytest.mark.parametrize("policy", [MODERN_ASSOCIATIONS, LEGACY_ASSOCIATIONS], ids=["modern", "legacy"])
@pytest.mark.parametrize("invalid", ["identity", "boolean-index", "reserved", "relative", "duplicate"])
def test_decoding_retains_format_specific_errors(policy, invalid):
    """Sharing the algorithm must not replace legacy field names or error messages."""
    entry = {"folder_id": "id", "index": 1, "directory_name": "storage", "original_path": "Z:/absolute"}
    entries = [entry]
    if invalid == "identity":
        entry["folder_id"] = ""
        expected = policy.identity_error
    elif invalid == "boolean-index":
        entry["index"] = True
        expected = f"{policy.subject} contains an invalid index for 'id'."
    elif invalid == "reserved":
        entry["directory_name"] = BACKUP_MANIFEST_NAME
        expected = policy.reserved_error
    elif invalid == "relative":
        entry["original_path"] = "relative"
        expected = f"{policy.subject} path for 'id' must be absolute."
    else:
        entries.append(dict(entry))
        expected = policy.duplicate_error
    with pytest.raises(ValueError) as error:
        parse_associations(entries, policy)
    assert str(error.value) == expected


def test_manifest_path_policy_keeps_native_plus_windows_flavours():
    """A generic any-platform predicate would broaden the old Windows policy."""
    entry = {"folder_id": "id", "index": 1, "directory_name": "storage", "original_path": "/source"}
    if os.name == "nt":
        with pytest.raises(ValueError, match="must be absolute"):
            parse_associations([entry], MODERN_ASSOCIATIONS)
    else:
        assert parse_associations([entry], MODERN_ASSOCIATIONS)[0].original_path == "/source"
