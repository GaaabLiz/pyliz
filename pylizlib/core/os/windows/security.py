"""Windows metadata adapter, loading native APIs only when called."""

from pathlib import Path


def copy_security(source: Path, destination: Path) -> None:
    """Copy the Windows owner, group and discretionary access control list."""
    try:
        import win32security
    except ImportError as error:
        raise NotImplementedError("Extended Windows security copying requires pywin32.") from error

    security_information = win32security.OWNER_SECURITY_INFORMATION | win32security.GROUP_SECURITY_INFORMATION | win32security.DACL_SECURITY_INFORMATION
    descriptor = win32security.GetFileSecurity(str(source), security_information)
    win32security.SetFileSecurity(str(destination), security_information, descriptor)
