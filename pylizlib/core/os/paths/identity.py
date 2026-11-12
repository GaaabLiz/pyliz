"""Compare path spellings and filesystem aliases without requiring existence."""

from pathlib import Path


def same_filesystem_entry(first: str | Path, second: str | Path) -> bool:
    """Return whether two paths name the same existing filesystem entry.

    Path equality handles the platform's lexical rules. ``samefile`` adds the
    filesystem's own rules for aliases such as symbolic links and
    case-insensitive names. Missing entries are not equivalent unless their
    paths compare equal lexically.

    Args:
        first (str | Path): First native-platform path; it need not exist.
        second (str | Path): Path to compare with first.

    Returns:
        bool: True for equal lexical paths or aliases of one existing entry. False for unequal paths when either
            entry is missing.

    Raises:
        ValueError: If an OS error other than a missing entry prevents comparison. The original OSError remains
            available as the exception cause.
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
