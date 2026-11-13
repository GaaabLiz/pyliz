"""Tests for the shared guard used before destructive filesystem operations."""

import platform
from pathlib import Path
from unittest.mock import patch

import pytest

from pylizlib.core.os.snap.operations import destinations
from pylizlib.core.os.snap.operations.destinations import validate_destructive_destinations


@pytest.fixture
def validate_noncritical_destinations(monkeypatch):
    """Isolate overlap checks from the host's system-directory layout."""
    monkeypatch.setattr(destinations, "is_critical_system_path", lambda path: False)
    return validate_destructive_destinations


def test_validator_returns_absolute_paths_for_disjoint_destinations(tmp_path, validate_noncritical_destinations):
    """Safe independent destinations are returned in input order."""
    catalogue = tmp_path / "catalogue"
    first = tmp_path / "one"
    second = tmp_path / "two"

    result = validate_noncritical_destinations(
        [("one", first), ("two", second)],
        catalogue_path=catalogue,
        origin_os=platform.system(),
        operation="test operation",
    )

    assert result == [first, second]
    assert all(path.is_absolute() for path in result)


@pytest.mark.parametrize(
    ("first_name", "second_name"),
    [("same", "same"), ("project", "project/cache"), ("project/cache", "project")],
)
def test_validator_rejects_coincident_or_nested_destinations(tmp_path, first_name, second_name, validate_noncritical_destinations):
    """Destinations that could move or delete one another are rejected."""
    with pytest.raises(ValueError, match="cannot be coincident or nested"):
        validate_noncritical_destinations(
            [("first", tmp_path / first_name), ("second", tmp_path / second_name)],
            catalogue_path=tmp_path / "catalogue",
            origin_os=platform.system(),
            operation="test operation",
        )


@pytest.mark.parametrize("target", ["catalogue", ".", "catalogue/snapshot"])
def test_validator_rejects_paths_that_overlap_the_catalogue(tmp_path, target, validate_noncritical_destinations):
    """A destructive destination cannot contain or be inside catalogue storage."""
    catalogue = tmp_path / "catalogue"
    destination = catalogue if target == "catalogue" else (tmp_path if target == "." else catalogue / "snapshot")

    with pytest.raises(ValueError, match="overlaps the snapshot catalogue"):
        validate_noncritical_destinations(
            [("association", destination)],
            catalogue_path=catalogue,
            origin_os=platform.system(),
            operation="test operation",
        )


def test_validator_rejects_catalogue_overlap_through_a_symlink_alias(tmp_path, validate_noncritical_destinations):
    """Resolved aliases cannot disguise a destination inside the catalogue."""
    catalogue = tmp_path / "catalogue"
    catalogue.mkdir()
    alias = tmp_path / "catalogue_alias"
    alias.symlink_to(catalogue, target_is_directory=True)

    with pytest.raises(ValueError, match="overlaps the snapshot catalogue"):
        validate_noncritical_destinations(
            [("association", alias / "snapshot")],
            catalogue_path=catalogue,
            origin_os=platform.system(),
            operation="test operation",
        )


def test_validator_checks_filesystem_identity_separately_from_resolved_strings(tmp_path, monkeypatch, validate_noncritical_destinations):
    """Equivalent existing targets are rejected even if resolution leaves both spellings intact."""
    first = tmp_path / "target"
    first.mkdir()
    alias = tmp_path / "target_alias"
    try:
        alias.symlink_to(first, target_is_directory=True)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"symlink creation is unavailable: {error}")

    # Some filesystems do not canonicalize every alias in resolve(); samefile
    # supplies a separate check against the underlying filesystem identity.
    monkeypatch.setattr(Path, "resolve", lambda path, strict=False: path.absolute())

    with pytest.raises(ValueError, match="cannot be coincident or nested"):
        validate_noncritical_destinations(
            [("first", first), ("alias", alias)],
            catalogue_path=tmp_path / "catalogue",
            origin_os=platform.system(),
            operation="test operation",
        )


def test_validator_rejects_paths_that_cannot_be_resolved(tmp_path, validate_noncritical_destinations):
    """A resolution error blocks work instead of treating the path as verified."""
    with patch.object(Path, "resolve", side_effect=OSError("resolution failed")):
        with pytest.raises(ValueError, match="Cannot verify destructive destination"):
            validate_noncritical_destinations(
                [("association", tmp_path / "target")],
                catalogue_path=tmp_path / "catalogue",
                origin_os=platform.system(),
                operation="test operation",
            )


def test_validator_rejects_snapshots_from_another_operating_system(tmp_path, validate_noncritical_destinations):
    """A destination is never touched using a snapshot from another OS."""
    other_os = "not-" + platform.system()

    with pytest.raises(RuntimeError, match="created on"):
        validate_noncritical_destinations(
            [("association", tmp_path / "target")],
            catalogue_path=tmp_path / "catalogue",
            origin_os=other_os,
            operation="test operation",
        )
