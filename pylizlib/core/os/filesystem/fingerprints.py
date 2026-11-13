"""SHA-256 tree fingerprints for detecting observable source changes."""

import hashlib
import os
import stat
from pathlib import Path

from pylizlib.core.os.filesystem.tree import assert_no_symlinks
from pylizlib.core.os.filesystem.tree import is_link_or_junction as _is_link_or_junction


def fingerprint_tree(root: Path) -> dict[str, tuple[str, int | str]]:
    """Fingerprint source files and directories, rejecting links and special files.

    This scan representation is distinct from the persisted integrity manifest.

    Args:
        root (Path): Root directory for the tree operation; link and existence policy is described above.

    Returns:
        dict[str, tuple[str, int | str]]: Relative path fingerprint preserving empty directories, file SHA-256
            digests and byte sizes.

    Raises:
        NotADirectoryError: A required real directory is missing, is a link, or has another entry type.
        ValueError: A value, path, resource limit or metadata field violates the validation rules described above.
    """
    assert_no_symlinks(root)
    root_mode = root.lstat().st_mode
    if _is_link_or_junction(root) or not stat.S_ISDIR(root_mode):
        raise NotADirectoryError(f"Copy source '{root}' is not a real directory.")

    manifest: dict[str, tuple[str, int | str]] = {".": ("directory", 0)}
    pending = [root]
    while pending:
        current = pending.pop()
        with os.scandir(current) as entries:
            for entry in entries:
                relative = Path(entry.path).relative_to(root).as_posix()
                entry_path = Path(entry.path)
                mode = entry.stat(follow_symlinks=False).st_mode
                if stat.S_ISLNK(mode) or _is_link_or_junction(entry_path):
                    raise ValueError(f"Verified copy does not accept symbolic links: '{entry.path}'.")
                if stat.S_ISDIR(mode):
                    manifest[relative] = ("directory", 0)
                    pending.append(Path(entry.path))
                elif stat.S_ISREG(mode):
                    digest = hashlib.sha256()
                    with Path(entry.path).open("rb") as file:
                        for chunk in iter(lambda: file.read(1024 * 1024), b""):
                            digest.update(chunk)
                    manifest[relative] = (digest.hexdigest(), entry.stat(follow_symlinks=False).st_size)
                else:
                    raise ValueError(f"Verified copy does not accept special file '{entry.path}'.")
    return manifest
