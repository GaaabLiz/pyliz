"""Observed stored manifests reuse strict general file hashing and empty-directory scans."""

import hashlib

from pylizlib.core.os.snap.integrity import build_integrity_manifest, validate_integrity_manifest


def test_observed_manifest_includes_root_empty_directories_and_exact_binary_bytes(tmp_path):
    """Filesystem fingerprints are adapted to the persisted snapshot schema without losing entries."""
    (tmp_path / "empty").mkdir()
    content = b"\x00\xffbinary\r\n"
    (tmp_path / "payload").write_bytes(content)
    observed = build_integrity_manifest(tmp_path)
    assert observed == {
        ".": {"type": "directory", "size": 0, "sha256": None},
        "empty": {"type": "directory", "size": 0, "sha256": None},
        "payload": {"type": "file", "size": len(content), "sha256": hashlib.sha256(content).hexdigest()},
    }
    assert validate_integrity_manifest(observed) is None
