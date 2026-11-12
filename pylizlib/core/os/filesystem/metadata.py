"""Copy ownership, extended attributes and hard-link topology of file trees."""

import errno
import os
import shutil
import stat
from collections.abc import Callable
from pathlib import Path

from pylizlib.core.os.filesystem.tree import assert_no_symlinks, iter_tree_entries_strict
from pylizlib.core.os.windows.security import copy_security
from pylizlib.core.os.windows.streams import copy_streams


def copy_extended_attributes(source: Path, destination: Path) -> None:
    """Copy every extended attribute exposed by the local Python runtime."""
    list_xattr = getattr(os, "listxattr", None)
    get_xattr = getattr(os, "getxattr", None)
    set_xattr = getattr(os, "setxattr", None)
    if not all((list_xattr, get_xattr, set_xattr)):
        return
    try:
        names = list_xattr(source, follow_symlinks=False)
    except OSError as error:
        unsupported = {getattr(errno, "ENOTSUP", -1), getattr(errno, "EOPNOTSUPP", -2), getattr(errno, "ENOSYS", -3)}
        if error.errno in unsupported:
            return
        raise
    for name in names:
        value = get_xattr(source, name, follow_symlinks=False)
        set_xattr(destination, name, value, follow_symlinks=False)


def copy_posix_owner_group(source: Path, destination: Path) -> None:
    """Copy POSIX ownership when the caller has the required privilege."""
    source_stat = source.stat(follow_symlinks=False)
    destination_stat = destination.stat(follow_symlinks=False)
    if (source_stat.st_uid, source_stat.st_gid) == (destination_stat.st_uid, destination_stat.st_gid):
        return
    chown = getattr(os, "chown", None)
    if chown is None:
        raise NotImplementedError("This platform cannot copy POSIX ownership.")
    chown(destination, source_stat.st_uid, source_stat.st_gid)


class TreeMetadataCopier:
    """Preserve supported metadata on a fully copied, link-free destination tree."""

    def __init__(
        self,
        *,
        owner_group: Callable[[Path, Path], None] = copy_posix_owner_group,
        attributes: Callable[[Path, Path], None] = copy_extended_attributes,
        windows_streams: Callable[[Path, Path], None] = copy_streams,
        windows_security: Callable[[Path, Path], None] = copy_security,
    ):
        """Select metadata backends without reading either tree."""
        self.copy_owner_group = owner_group
        self.copy_attributes = attributes
        self.copy_streams = windows_streams
        self.copy_security = windows_security

    def preserve(self, source: Path, destination: Path) -> None:
        """Apply extended metadata to a fully copied, link-free staging tree."""
        assert_no_symlinks(source)
        assert_no_symlinks(destination)
        entries = [(source, destination)]
        entries.extend((path, destination / path.relative_to(source)) for path in iter_tree_entries_strict(source))

        file_entries = []
        directory_entries = []
        hardlink_groups: dict[tuple[int, int], list[Path]] = {}
        for source_path, destination_path in entries:
            mode = source_path.lstat().st_mode
            if stat.S_ISDIR(mode):
                directory_entries.append((source_path, destination_path))
            elif stat.S_ISREG(mode):
                file_entries.append((source_path, destination_path))
                source_stat = source_path.stat(follow_symlinks=False)
                if source_stat.st_nlink > 1:
                    if not source_stat.st_ino:
                        raise NotImplementedError(f"Cannot identify hard links for '{source_path}' on this filesystem.")
                    hardlink_groups.setdefault((source_stat.st_dev, source_stat.st_ino), []).append(destination_path)
            else:
                raise ValueError(f"Extended metadata copy does not accept special file '{source_path}'.")

        # Recreate hard links inside this tree before applying inode metadata.
        for destinations in hardlink_groups.values():
            if len(destinations) > 1:
                first, *duplicates = destinations
                for duplicate in duplicates:
                    duplicate.unlink()
                    os.link(first, duplicate)

        unique_files = []
        seen_inodes = set()
        for source_path, destination_path in file_entries:
            source_stat = source_path.stat(follow_symlinks=False)
            identity = (source_stat.st_dev, source_stat.st_ino)
            if identity not in seen_inodes:
                seen_inodes.add(identity)
                unique_files.append((source_path, destination_path))

        ordered_entries = unique_files + sorted(directory_entries, key=lambda pair: len(pair[0].parts), reverse=True)
        for source_path, destination_path in ordered_entries:
            if os.name == "nt":
                self.copy_streams(source_path, destination_path)
            else:
                self.copy_owner_group(source_path, destination_path)
            # Ownership changes can clear set-id or capability bits.
            shutil.copystat(source_path, destination_path, follow_symlinks=False)
            if os.name != "nt":
                # Apply ACL xattrs after copystat because chmod can adjust ACL masks.
                self.copy_attributes(source_path, destination_path)

        if os.name == "nt":
            # DACLs are applied last because a source ACL can deny the current
            # process access needed to finish metadata updates on the staging tree.
            for source_path, destination_path in ordered_entries:
                self.copy_security(source_path, destination_path)
