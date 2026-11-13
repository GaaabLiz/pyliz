"""Test native security adapter calls without claiming native Windows execution."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pylizlib.core.os.windows.security import grant_everyone_full_control


def test_everyone_grant_preserves_account_and_inheritance_flags(tmp_path):
    """The generic adapter retains the prior Everyone lookup and DACL update."""
    acl = Mock()
    descriptor = Mock()
    descriptor.GetSecurityDescriptorDacl.return_value = acl
    api = SimpleNamespace(
        LookupAccountName=Mock(return_value=("sid", "domain", "type")), GetFileSecurity=Mock(return_value=descriptor), SetFileSecurity=Mock(), DACL_SECURITY_INFORMATION=4, ACL_REVISION=2
    )
    constants = SimpleNamespace(OBJECT_INHERIT_ACE=1, CONTAINER_INHERIT_ACE=2, GENERIC_ALL=256)

    grant_everyone_full_control(tmp_path, security_api=api, con=constants)

    api.LookupAccountName.assert_called_once_with("", "Everyone")
    acl.AddAccessAllowedAceEx.assert_called_once_with(2, 3, 256, "sid")
    descriptor.SetSecurityDescriptorDacl.assert_called_once_with(1, acl, 0)
    api.SetFileSecurity.assert_called_once_with(str(tmp_path), 4, descriptor)
    api.LookupAccountName.side_effect = PermissionError("denied")
    with pytest.raises(PermissionError, match="denied"):
        grant_everyone_full_control(tmp_path, security_api=api, con=constants)
