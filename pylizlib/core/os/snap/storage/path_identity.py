"""Filesystem-level path identity checks shared by snapshot operations."""

from pathlib import Path


def same_filesystem_entry(first: str | Path, second: str | Path) -> bool:
    """Return whether two paths name the same existing filesystem entry.

    Path equality handles the platform's lexical rules. ``samefile`` adds the
    filesystem's own rules for aliases such as symbolic links and
    case-insensitive names. Missing entries are not equivalent unless their
    paths compare equal lexically.
    """
    first_path = Path(first)
    second_path = Path(second)
    if first_path == second_path:
        return True
    try:
        return first_path.samefile(second_path)
    except FileNotFoundError:
        return False
    except OSError as error:
        raise ValueError(f"Cannot verify whether paths '{first_path}' and '{second_path}' are equivalent: {error}") from error
