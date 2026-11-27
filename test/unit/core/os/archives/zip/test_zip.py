"""ZIP primitives operate on general files without snapshot metadata."""

import os
import stat
import zipfile

import pytest

from pylizlib.core.os.archives.zip.extraction import extract_zip
from pylizlib.core.os.archives.zip.publication import write_verified_zip_exclusive
from pylizlib.core.os.archives.zip.validation import validate_zip_archive


def test_verified_exclusive_publication_and_empty_directory_round_trip(tmp_path):
    """A collision preserves the old ZIP and extraction retains empty directories."""
    source = tmp_path / "empty"
    source.mkdir()
    archive = tmp_path / "data.zip"
    write_verified_zip_exclusive(archive, [(source, source.relative_to(tmp_path))])
    original = archive.read_bytes()
    with pytest.raises(FileExistsError):
        write_verified_zip_exclusive(archive, [])
    assert archive.read_bytes() == original
    assert validate_zip_archive(archive).entry_count == 1
    destination = tmp_path / "extracted"
    extract_zip(archive, destination)
    assert (destination / "empty").is_dir()
    assert not list(tmp_path.glob(".backup_*.partial"))


def test_preflight_rejects_traversal_before_creating_destination(tmp_path):
    """A structurally invalid member cannot create an extraction directory."""
    archive = tmp_path / "invalid.zip"
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr("../outside", "payload")
    destination = tmp_path / "extracted"
    with pytest.raises(ValueError, match="escapes"):
        extract_zip(archive, destination)
    assert not destination.exists()


@pytest.mark.skipif(os.name != "posix", reason="Unix executable bits require POSIX permissions")
def test_extraction_applies_unix_executable_bits_without_special_permissions(tmp_path):
    archive = tmp_path / "permissions.zip"
    with zipfile.ZipFile(archive, "w") as stream:
        for name, creator, mode in (("unix-script", 3, 0o4710), ("unix-text", 3, 0o644), ("other", 0, 0o755)):
            member = zipfile.ZipInfo(name)
            member.create_system = creator
            member.external_attr = (stat.S_IFREG | mode) << 16
            stream.writestr(member, "payload")

    destination = tmp_path / "extracted"
    extract_zip(archive, destination)

    assert (destination / "unix-script").stat().st_mode & 0o7111 == 0o110
    assert (destination / "unix-text").stat().st_mode & 0o111 == 0
    assert (destination / "other").stat().st_mode & 0o111 == 0
