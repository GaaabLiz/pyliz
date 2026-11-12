"""Copy ownership, extended attributes and hard-link topology of file trees."""

import errno
import os
import shutil
import stat
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from pylizlib.core.os.filesystem.tree import assert_no_symlinks, iter_tree_entries_strict
from pylizlib.core.os.windows.security import copy_security
from pylizlib.core.os.windows.streams import copy_streams


def copy_extended_attributes(source: Path, destination: Path) -> None:
    """Copy every extended attribute exposed by the local Python runtime.

    Args:
        source (Path): Source file or directory whose contents or metadata are read.
        destination (Path): Target path receiving the copied content or metadata.

    Returns:
        None: No return value.

    Raises:
        OSError: An available source attribute cannot be read or written to the target.

    Notes:
        Missing runtime xattr functions and source ENOTSUP/EOPNOTSUPP/ENOSYS are
        skipped. Once attributes are exposed, a target-side failure propagates.
    """
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
    """Copy POSIX ownership when the caller has the required privilege.

    Args:
        source (Path): Source file or directory whose contents or metadata are read.
        destination (Path): Target path receiving the copied content or metadata.

    Returns:
        None: No return value.

    Raises:
        NotImplementedError: The platform cannot provide required metadata or filesystem capabilities.
        OSError: Reading ownership or applying a required chown operation fails,
            including insufficient privilege. Equal source/target ownership needs no chown.
    """
    source_stat = source.stat(follow_symlinks=False)
    destination_stat = destination.stat(follow_symlinks=False)
    if (source_stat.st_uid, source_stat.st_gid) == (destination_stat.st_uid, destination_stat.st_gid):
        return
    chown = getattr(os, "chown", None)
    if chown is None:
        raise NotImplementedError("This platform cannot copy POSIX ownership.")
    chown(destination, source_stat.st_uid, source_stat.st_gid)


@dataclass(frozen=True)
class MetadataTree:
    """Retain file pairs, directory pairs and hard-link groups for one metadata pass.

    Attributes:
        files (list[tuple[Path, Path]]): Source/target regular-file pairs in visit order.
        directories (list[tuple[Path, Path]]): Source/target directories, including root.
        hardlink_groups (dict[tuple[int, int], list[Path]]): Target paths grouped by source device/inode. Only
            entries with multiple source links are grouped.
    """

    files: list[tuple[Path, Path]]
    directories: list[tuple[Path, Path]]
    hardlink_groups: dict[tuple[int, int], list[Path]]


class TreeMetadataCopier:
    """Preserve supported metadata on a fully copied, link-free destination tree.

    Attributes:
        copy_owner_group (Callable[[Path, Path], None]): POSIX owner/group backend for copied entries.
        copy_attributes (Callable[[Path, Path], None]): Extended-attribute backend applied after standard stat
            copying.
        copy_streams (Callable[[Path, Path], None]): Windows named-stream backend used before copying security
            descriptors.
        copy_security (Callable[[Path, Path], None]): Windows owner/group/DACL backend applied after all other
            metadata work.
    """

    def __init__(
        self,
        *,
        owner_group: Callable[[Path, Path], None] = copy_posix_owner_group,
        attributes: Callable[[Path, Path], None] = copy_extended_attributes,
        windows_streams: Callable[[Path, Path], None] = copy_streams,
        windows_security: Callable[[Path, Path], None] = copy_security,
    ):
        """Select metadata backends without reading either tree.

        Args:
            owner_group (Callable[[Path, Path], None]): Backend applying source owner/group to an existing copied
                entry.
            attributes (Callable[[Path, Path], None]): Backend applying source extended attributes to an existing
                copied entry.
            windows_streams (Callable[[Path, Path], None]): Backend copying named Windows data streams while source
                and target remain accessible.
            windows_security (Callable[[Path, Path], None]): Backend copying Windows owner/group/DACL after other
                metadata work.

        Returns:
            None: No return value.
        """
        self.copy_owner_group = owner_group
        self.copy_attributes = attributes
        self.copy_streams = windows_streams
        self.copy_security = windows_security

    def preserve(self, source: Path, destination: Path) -> None:
        """Apply extended metadata to a fully copied, link-free staging tree.

        Args:
            source (Path): Source file or directory whose contents or metadata are read.
            destination (Path): Target path receiving the copied content or metadata.

        Returns:
            None: No return value.
        """
        assert_no_symlinks(source)
        assert_no_symlinks(destination)

        # Collect topology before replacing any destination hard links.
        tree = self._collect_entries(source, destination)
        self._recreate_hardlinks(tree.hardlink_groups)

        # Inode metadata is applied once per file, then to deepest directories first.
        ordered_entries = self._order_entries(tree)
        self._apply_entry_metadata(ordered_entries)

    @staticmethod
    def _collect_entries(source: Path, destination: Path) -> MetadataTree:
        """Inspect source topology and pair each regular entry with its copied target.

        Args:
            source (Path): Source file or directory whose contents or metadata are read.
            destination (Path): Target path receiving the copied content or metadata.

        Returns:
            MetadataTree: File/directory source-target pairs and destination hard-link groups for this metadata pass.

        Raises:
            NotImplementedError: The platform cannot provide required metadata or filesystem capabilities.
            ValueError: A value, path, resource limit or metadata field violates the validation rules described above.
        """
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
        return MetadataTree(file_entries, directory_entries, hardlink_groups)

    @staticmethod
    def _recreate_hardlinks(hardlink_groups: dict[tuple[int, int], list[Path]]) -> None:
        """Recreate destination hard links before inode metadata is applied.

        Args:
            hardlink_groups (dict[tuple[int, int], list[Path]]): Destination paths grouped by source device/inode
                before metadata is applied.

        Returns:
            None: No return value.
        """
        for destinations in hardlink_groups.values():
            if len(destinations) > 1:
                first, *duplicates = destinations
                for duplicate in duplicates:
                    duplicate.unlink()
                    os.link(first, duplicate)

    @staticmethod
    def _order_entries(tree: MetadataTree) -> list[tuple[Path, Path]]:
        """Deduplicate source inodes, then order directories from deepest to root.

        Args:
            tree (MetadataTree): Collected source/target topology, including directory pairs and hard-link groups.

        Returns:
            list[tuple[Path, Path]]: One file pair per source inode followed by directories ordered deepest first,
                including root.
        """
        file_entries = tree.files
        directory_entries = tree.directories
        unique_files = []
        seen_inodes = set()
        for source_path, destination_path in file_entries:
            source_stat = source_path.stat(follow_symlinks=False)
            identity = (source_stat.st_dev, source_stat.st_ino)
            if identity not in seen_inodes:
                seen_inodes.add(identity)
                unique_files.append((source_path, destination_path))

        ordered_entries = unique_files + sorted(directory_entries, key=lambda pair: len(pair[0].parts), reverse=True)
        return ordered_entries

    def _apply_entry_metadata(self, ordered_entries: list[tuple[Path, Path]]) -> None:
        """Apply ownership/streams, stat and xattrs, with Windows DACLs last.

        Args:
            ordered_entries (list[tuple[Path, Path]]): Unique-file and deepest-directory-first source/target pairs
                ready for metadata copying.

        Returns:
            None: No return value.
        """
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
