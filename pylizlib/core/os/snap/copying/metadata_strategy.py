"""Strategy that adds strict extended metadata to copied directory trees."""

from __future__ import annotations

import tempfile
from collections.abc import Mapping, MutableMapping
from pathlib import Path

from pylizlib.core.os.filesystem.metadata import TreeMetadataCopier, copy_extended_attributes, copy_posix_owner_group
from pylizlib.core.os.snap.callbacks import CopyProgressCallback as ProgressCallback
from pylizlib.core.os.snap.callbacks import MessageCallback
from pylizlib.core.os.snap.copy_strategy import DirectoryCopyStrategy
from pylizlib.core.os.snap.copying.contracts import MetadataCopyCapability
from pylizlib.core.os.snap.storage.tree import assert_destination_outside_source, assert_no_symlinks
from pylizlib.core.os.windows.security import copy_security
from pylizlib.core.os.windows.streams import copy_streams


class _ExtendedMetadataCopyStrategy(DirectoryCopyStrategy):
    """Decorate a copy strategy with strict, platform-supported metadata copying.

    The delegate continues to copy file contents and standard metadata. This
    strategy additionally restores the copied root directory metadata, owner
    and group where available, extended attributes (including Linux ACL
    attributes), Windows owner/group/DACL and alternate data streams, and
    hard-link relationships that exist within the copied tree. Missing runtime/source xattr support is skipped under the existing policy.
    Failures copying exposed attributes or other required metadata abort instead
    of silently publishing a weaker result. Filesystem-specific metadata outside these APIs cannot be promised.

    Attributes:
        delegate (DirectoryCopyStrategy): Content-copy strategy retained by reference, preserving its consistency
            and callback contract.
    """

    def __init__(self, delegate: DirectoryCopyStrategy):
        """Wrap one directory copy strategy without changing its content policy.

        Args:
            delegate (DirectoryCopyStrategy): Content-copy strategy retained by reference, preserving its consistency
                and callback contract.

        Returns:
            None: No return value.

        Raises:
            TypeError: An argument or mutable model field has a type rejected by this contract.
        """
        if not isinstance(delegate, DirectoryCopyStrategy):
            raise TypeError("delegate must implement DirectoryCopyStrategy.")
        self.delegate = delegate

    @staticmethod
    def _copy_extended_attributes(source: Path, destination: Path) -> None:
        """Copy every extended attribute exposed by the local Python runtime.

        Args:
            source (Path): Source file or directory whose contents or metadata are read.
            destination (Path): Target path receiving the copied content or metadata.

        Returns:
            None: No return value.
        """
        copy_extended_attributes(source, destination)

    @staticmethod
    def _copy_posix_owner_group(source: Path, destination: Path) -> None:
        """Copy POSIX ownership when the caller has the required privilege.

        Args:
            source (Path): Source file or directory whose contents or metadata are read.
            destination (Path): Target path receiving the copied content or metadata.

        Returns:
            None: No return value.
        """
        copy_posix_owner_group(source, destination)

    @staticmethod
    def _copy_windows_security(source: Path, destination: Path) -> None:
        """Copy the Windows owner, group and discretionary access control list.

        Args:
            source (Path): Source file or directory whose contents or metadata are read.
            destination (Path): Target path receiving the copied content or metadata.

        Returns:
            None: No return value.
        """
        copy_security(source, destination)

    @staticmethod
    def _copy_windows_streams(source: Path, destination: Path) -> None:
        """Copy NTFS alternate data streams exposed by FindFirstStreamW.

        Args:
            source (Path): Source file or directory whose contents or metadata are read.
            destination (Path): Target path receiving the copied content or metadata.

        Returns:
            None: No return value.
        """
        copy_streams(source, destination)

    @classmethod
    def _preserve_metadata(cls, source: Path, destination: Path) -> None:
        """Apply extended metadata to a fully copied, link-free staging tree.

        Args:
            source (Path): Source file or directory whose contents or metadata are read.
            destination (Path): Target path receiving the copied content or metadata.

        Returns:
            None: No return value.
        """
        TreeMetadataCopier(
            owner_group=cls._copy_posix_owner_group, attributes=cls._copy_extended_attributes, windows_streams=cls._copy_windows_streams, windows_security=cls._copy_windows_security
        ).preserve(source, destination)

    def copy_directory(
        self,
        source: Path,
        destination: Path,
        progress_callback: ProgressCallback | None = None,
        message_callback: MessageCallback | None = None,
        *,
        manifest: MutableMapping[str, dict[str, str | int | None]] | None = None,
        expected_manifest: Mapping[str, dict[str, str | int | None]] | None = None,
    ) -> Path:
        """Stage the delegate copy, enrich metadata, then publish it as a unit.

        Args:
            source (Path): Source file or directory whose contents or metadata are read.
            destination (Path): Target path receiving the copied content or metadata.
            progress_callback (ProgressCallback | None): Optional observer receiving (copied_bytes, total_bytes),
                including terminal empty-tree progress; return values do not cancel copying.
            message_callback (MessageCallback | None): Optional status observer receiving one message string; its
                exceptions propagate according to the calling operation.
            manifest (MutableMapping[str, dict[str, str | int | None]] | None): Optional mutable captured-integrity
                output, replaced only on successful copy. expected_manifest can still require verification when this
                is None.
            expected_manifest (Mapping[str, dict[str, str | int | None]] | None): Previously captured integrity
                mapping to verify before publishing; None disables this comparison.

        Returns:
            Path: Final destination after successful content verification/publication. Any supplied output manifest is
                updated only on success.

        Raises:
            FileExistsError: A destination or generated staging name already exists or changes before publication.

        Notes:
            A delegate advertising MetadataCopyCapability applies metadata inside its own stable-source lifetime.
            Other delegates retain the existing live-source metadata pass. Unsupported required metadata copying fails
            rather than silently weakening the result.
        """
        source = Path(source)
        destination = Path(destination)
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(f"Copy destination '{destination}' already exists.")
        assert_destination_outside_source(source, destination)
        assert_no_symlinks(source)
        destination.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix=".extended_metadata_", dir=destination.parent) as temporary_directory:
            staged = Path(temporary_directory) / "copy"
            staged_manifest = {} if manifest is not None else None
            supports_metadata_copy = isinstance(self.delegate, MetadataCopyCapability)
            if supports_metadata_copy:
                self.delegate.copy_directory_with_metadata(
                    source,
                    staged,
                    progress_callback,
                    message_callback,
                    manifest=staged_manifest,
                    expected_manifest=expected_manifest,
                    metadata_copier=_ExtendedMetadataCopyStrategy._preserve_metadata,
                )
            else:
                self.delegate.copy_directory(
                    source,
                    staged,
                    progress_callback,
                    message_callback,
                    manifest=staged_manifest,
                    expected_manifest=expected_manifest,
                )
            if not supports_metadata_copy:
                self._preserve_metadata(source, staged)
            if destination.exists() or destination.is_symlink():
                raise FileExistsError(f"Copy destination '{destination}' was created during copying.")
            staged.rename(destination)
            if manifest is not None:
                manifest.clear()
                manifest.update(staged_manifest or {})
        return destination
