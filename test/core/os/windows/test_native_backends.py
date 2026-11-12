"""Native Windows conformance checks; mocks cover failure paths separately.

Only a configured mapped drive is optional beyond the filesystem/privilege
capabilities explicitly reported by each test. These tests must run on Windows
before changing a native backend; passing them on another OS is impossible.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from pylizlib.core.os.filesystem.tree import assert_no_symlinks
from pylizlib.core.os.windows.drives import get_drive_type, get_mapped_drive_unc_root
from pylizlib.core.os.windows.security import copy_security
from pylizlib.core.os.windows.streams import copy_streams

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Requires native Windows APIs and filesystem semantics")


def test_native_drive_type_agrees_with_pywin32():
    """The extracted adapter retains the system drive's native classification."""
    import win32file

    drive = Path(os.environ["SystemRoot"]).drive
    assert get_drive_type(drive.removesuffix(":")) == win32file.GetDriveType(f"{drive}\\")


def test_native_mapped_drive_matches_current_logon_mapping():
    """A provisioned network drive exposes the same UNC root through both APIs."""
    import win32wnet

    drive = os.environ.get("PYLIZ_TEST_MAPPED_DRIVE", "").removesuffix(":")
    if not drive:
        pytest.skip("Set PYLIZ_TEST_MAPPED_DRIVE to a provisioned drive letter for a real network mapping test")
    assert get_drive_type(drive) == 4
    assert get_mapped_drive_unc_root(drive) == win32wnet.WNetGetConnection(f"{drive}:")


def test_native_stream_copy_preserves_named_and_unnamed_content(tmp_path):
    """Copy several ADS while leaving the caller-owned default stream untouched."""
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.write_bytes(b"source main")
    destination.write_bytes(b"destination main")
    streams = {":pyliz-one": b"first stream", ":pyliz-two": bytes(range(256))}
    try:
        for suffix, content in streams.items():
            Path(f"{source}{suffix}").write_bytes(content)
    except OSError as error:
        if error.winerror in (1, 50):
            pytest.skip(f"Temporary volume does not support named streams: {error}")
        raise
    copy_streams(source, destination)
    assert source.read_bytes() == b"source main"
    assert destination.read_bytes() == b"destination main"
    assert {suffix: Path(f"{destination}{suffix}").read_bytes() for suffix in streams} == streams


def test_native_security_copy_preserves_owner_group_and_distinct_dacl(tmp_path):
    """A real modified source DACL reaches the target without changing its data."""
    import ntsecuritycon
    import pywintypes
    import win32security

    source, destination, probe = (tmp_path / name for name in ("source", "destination", "privilege-probe"))
    for path in (source, destination, probe):
        path.write_bytes(b"content")
    flags = win32security.OWNER_SECURITY_INFORMATION | win32security.GROUP_SECURITY_INFORMATION | win32security.DACL_SECURITY_INFORMATION
    descriptor = win32security.GetFileSecurity(str(source), flags)
    acl = descriptor.GetSecurityDescriptorDacl()
    acl.AddAccessAllowedAceEx(win32security.ACL_REVISION, 0, ntsecuritycon.FILE_GENERIC_READ, descriptor.GetSecurityDescriptorOwner())
    descriptor.SetSecurityDescriptorDacl(1, acl, 0)
    win32security.SetFileSecurity(str(source), win32security.DACL_SECURITY_INFORMATION, descriptor)
    descriptor = win32security.GetFileSecurity(str(source), flags)
    try:
        win32security.SetFileSecurity(str(probe), flags, descriptor)
    except pywintypes.error as error:
        if error.winerror in (5, 1314):
            pytest.skip(f"Runner cannot set owner/group security information: {error}")
        raise

    def as_sddl(path):
        """Compare the native owner/group/DACL representation before and after."""
        security = win32security.GetFileSecurity(str(path), flags)
        return win32security.ConvertSecurityDescriptorToStringSecurityDescriptor(security, win32security.SDDL_REVISION_1, flags)

    assert as_sddl(source) != as_sddl(destination)
    copy_security(source, destination)
    assert as_sddl(destination) == as_sddl(source)
    assert destination.read_bytes() == b"content"


def test_native_junction_is_rejected_without_visiting_its_target(tmp_path):
    """The general traversal policy recognizes a real Windows reparse point."""
    source = tmp_path / "source"
    target = tmp_path / "outside"
    source.mkdir()
    target.mkdir()
    (target / "keep").write_bytes(b"unchanged")
    junction = source / "junction"
    result = subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(target)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    try:
        assert junction.is_junction()
        with pytest.raises(ValueError, match="symbolic link|junction"):
            assert_no_symlinks(source)
        assert (target / "keep").read_bytes() == b"unchanged"
    finally:
        junction.rmdir()
