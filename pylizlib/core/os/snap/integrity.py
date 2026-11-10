"""Integrity manifests for snapshot directory contents."""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import TypeAlias

ManifestEntry: TypeAlias = dict[str, str | int | None]
IntegrityManifest: TypeAlias = dict[str, ManifestEntry]
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class SnapshotIntegrityError(RuntimeError):
    """Raised when copied snapshot contents do not match their manifest."""


def validate_integrity_manifest(manifest: IntegrityManifest | None) -> None:
    """Validate a serialized tree manifest and all of its relative paths."""
    if manifest is None:
        return
    if not isinstance(manifest, dict):
        raise TypeError("Snapshot integrity manifest must be an object or None.")

    for relative_path, entry in manifest.items():
        if not isinstance(relative_path, str) or not relative_path or "\\" in relative_path or "\x00" in relative_path:
            raise ValueError("Snapshot manifest paths must be non-empty POSIX relative paths.")
        path = PurePosixPath(relative_path)
        if path.is_absolute() or any(part in {"", ".."} for part in path.parts):
            raise ValueError(f"Snapshot manifest path escapes its directory: {relative_path!r}.")
        if relative_path != "." and path.as_posix() != relative_path:
            raise ValueError(f"Snapshot manifest path is not normalized: {relative_path!r}.")
        if not isinstance(entry, dict) or set(entry) != {"type", "size", "sha256"}:
            raise ValueError(f"Invalid manifest entry for {relative_path!r}.")
        entry_type = entry["type"]
        size = entry["size"]
        digest = entry["sha256"]
        if entry_type not in {"file", "directory"}:
            raise ValueError(f"Invalid manifest entry type for {relative_path!r}.")
        if type(size) is not int or size < 0:
            raise ValueError(f"Invalid manifest size for {relative_path!r}.")
        if entry_type == "directory":
            if size != 0 or digest is not None:
                raise ValueError(f"Directory manifest entries must have size 0 and no hash: {relative_path!r}.")
        elif not isinstance(digest, str) or not _SHA256_PATTERN.fullmatch(digest):
            raise ValueError(f"Invalid SHA-256 hash for {relative_path!r}.")

    root = manifest.get(".")
    if root != {"type": "directory", "size": 0, "sha256": None}:
        raise ValueError("Snapshot integrity manifest must contain a root directory entry.")


def assert_manifest_matches(expected: IntegrityManifest, observed: IntegrityManifest) -> None:
    """Raise a useful error if expected and copied tree entries differ."""
    validate_integrity_manifest(expected)
    validate_integrity_manifest(observed)
    if expected == observed:
        return

    missing = sorted(expected.keys() - observed.keys())
    unexpected = sorted(observed.keys() - expected.keys())
    changed = sorted(
        path for path in expected.keys() & observed.keys() if expected[path] != observed[path]
    )
    details = []
    if missing:
        details.append(f"missing: {', '.join(missing[:5])}")
    if unexpected:
        details.append(f"unexpected: {', '.join(unexpected[:5])}")
    if changed:
        details.append(f"changed: {', '.join(changed[:5])}")
    raise SnapshotIntegrityError("Snapshot content does not match its integrity manifest (" + "; ".join(details) + ").")
