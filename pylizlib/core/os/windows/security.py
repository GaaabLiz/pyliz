"""Windows metadata adapter, loading native APIs only when called."""

from pathlib import Path


def copy_security(source: Path, destination: Path) -> None:
    """Copy the Windows owner, group and discretionary access control list.

    Args:
        source (Path): Source file or directory whose contents or metadata are read.
        destination (Path): Target path receiving the copied content or metadata.

    Returns:
        None: No return value.

    Raises:
        NotImplementedError: The platform cannot provide required metadata or filesystem capabilities.
    """
    try:
        import win32security
    except ImportError as error:
        raise NotImplementedError("Extended Windows security copying requires pywin32.") from error

    security_information = win32security.OWNER_SECURITY_INFORMATION | win32security.GROUP_SECURITY_INFORMATION | win32security.DACL_SECURITY_INFORMATION
    descriptor = win32security.GetFileSecurity(str(source), security_information)
    win32security.SetFileSecurity(str(destination), security_information, descriptor)


def grant_everyone_full_control(path: Path, *, security_api, con) -> None:
    """Add an inheritable Everyone full-control ACE using caller-supplied APIs.

    Args:
        path (Path): Installed directory whose existing DACL is extended.
        security_api (ModuleType): Loaded pywin32 security API, or compatible adapter.
        con (ModuleType): Loaded NT security constants used for access/inheritance flags.

    Returns:
        None: After replacing the directory's security descriptor DACL.

    Raises:
        Exception: Account lookup, descriptor, ACL and native write failures propagate so the calling policy can
            decide whether they are fatal.

    Notes:
        The historical account name Everyone is retained; SID/localization changes require a separate functional
        change. No dependency is loaded by this function.
    """
    everyone, domain, type = security_api.LookupAccountName("", "Everyone")
    sd = security_api.GetFileSecurity(str(path), security_api.DACL_SECURITY_INFORMATION)
    dacl = sd.GetSecurityDescriptorDacl()
    dacl.AddAccessAllowedAceEx(
        security_api.ACL_REVISION,
        con.OBJECT_INHERIT_ACE | con.CONTAINER_INHERIT_ACE,
        con.GENERIC_ALL,
        everyone,
    )
    sd.SetSecurityDescriptorDacl(1, dacl, 0)
    security_api.SetFileSecurity(str(path), security_api.DACL_SECURITY_INFORMATION, sd)
