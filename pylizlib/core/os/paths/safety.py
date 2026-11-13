"""Safety checks for paths that can replace or remove filesystem data."""

import os
import sys
from pathlib import Path


def assert_no_link_components(path: str | Path) -> None:
    """Reject symbolic links and junctions in a path before destructive use.

    Args:
        path (str | Path): Native path whose leaf and lexical ancestors are inspected. Relative paths are
            anchored to CWD without collapsing parent components.

    Returns:
        None: When no component is a link. Missing components are permitted so callers may create destinations.

    Raises:
        ValueError: A symbolic link or junction occurs in the path, including before a parent component.
        OSError: A component cannot be inspected.

    Notes:
        This check reserves no filesystem entry. Callers must revalidate before publication and coordinate their
        own concurrent operations; it does not follow a link to select a different destination.
    """

    # Filesystem traversal also imports path containment; defer this shared capability to the call.
    from pylizlib.core.os.filesystem.tree import is_link_or_junction

    lexical = Path(path).absolute()
    for component in (*reversed(lexical.parents), lexical):
        if is_link_or_junction(component):
            raise ValueError(f"Destructive path '{lexical}' contains a symbolic link or junction: '{component}'.")


def is_critical_system_path(path: str | Path) -> bool:
    """Check whether a path is critical, failing closed when it cannot be resolved.

    Args:
        path (str | Path): Candidate path to inspect.

    Returns:
        bool: Whether the path is a protected root or lies within a protected system path.
    """
    try:
        resolved_path = Path(path).resolve(strict=False)
    except Exception:
        return True

    if resolved_path == resolved_path.parent:
        return True

    try:
        home = Path.home().resolve(strict=False)
    except Exception:
        return True
    if resolved_path == home:
        return True

    critical_bases = [Path("/usr"), Path("/bin"), Path("/sbin"), Path("/etc"), Path("/var"), Path("/System")]
    if sys.platform == "win32":
        critical_bases.extend(
            [Path(os.environ.get("windir", "C:\\Windows")), Path(os.environ.get("ProgramFiles", "C:\\Program Files")), Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"))]
        )

    for critical_base in critical_bases:
        try:
            resolved_base = critical_base.resolve(strict=False)
            if resolved_path == resolved_base or resolved_path.is_relative_to(resolved_base):
                return True
        except Exception:
            return True

    return False
