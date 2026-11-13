"""Public copy strategy contracts and compatibility exports."""

from __future__ import annotations

import shutil
from abc import ABC, abstractmethod
from collections.abc import Mapping, MutableMapping
from enum import Enum
from pathlib import Path
from typing import ContextManager

from pylizlib.core.os.snap.callbacks import CopyProgressCallback as ProgressCallback
from pylizlib.core.os.snap.callbacks import MessageCallback
from pylizlib.core.os.snap.storage.tree import is_link_or_junction


class SourceChangedError(RuntimeError):
    """Raised when the source tree changes during each verified copy attempt."""


class CopyMetadataMode(str, Enum):
    """Select the metadata fidelity used while copying snapshot trees."""

    BASIC = "basic"
    EXTENDED = "extended"


class DirectoryCopyStrategy(ABC):
    """Common contract for copying a source directory into a new destination.

    Implementations must create ``destination`` on success and remove their
    partial destination if copying fails. The destination must not exist when
    the method starts. When ``manifest`` is supplied, implementations record
    files as they copy them; when ``expected_manifest`` is supplied, they must
    reject the copy before publishing if any path, type, size, or hash differs.
    Snapshot trees use one link policy: symlinks and junctions are rejected,
    never followed or silently omitted.
    """

    @abstractmethod
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
        """Copy a tree, optionally recording or validating its content manifest.

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
        """


def _remove_tree(path: Path) -> None:
    """Remove only the named entry, never follow a symlink at its root.

    Args:
        path (Path): Native filesystem entry operated on by this method.

    Returns:
        None: No return value.
    """
    if path.is_symlink():
        path.unlink(missing_ok=True)
    elif path.exists():
        shutil.rmtree(path)


def _is_link_or_junction(path: Path) -> bool:
    """Compatibility helper for the common storage entry check.

    Args:
        path (Path): Native filesystem entry operated on by this method.

    Returns:
        bool: Whether the entry is a symbolic link or Windows junction, including a dangling link.
    """
    return is_link_or_junction(path)


class SourceSnapshotProvider(ABC):
    """Adapter for a filesystem, server, or application snapshot facility."""

    @abstractmethod
    def create_snapshot(self, source: Path) -> ContextManager[Path]:
        """Yield a stable point-in-time directory for ``source``.

        Args:
            source (Path): Source file or directory whose contents or metadata are read.

        Returns:
            ContextManager[Path]: Context manager yielding an immutable or writer-quiesced directory for the whole
                context. The provider owns its lifetime and consistency guarantee.
        """


from pylizlib.core.os.snap.copying.file_strategies import _SequentialFileCopyStrategy as _SequentialFileCopyStrategy  # noqa: E402
from pylizlib.core.os.snap.copying.file_strategies import _VerifiedFileCopyStrategy as _VerifiedFileCopyStrategy  # noqa: E402
from pylizlib.core.os.snap.copying.metadata_strategy import _ExtendedMetadataCopyStrategy as _ExtendedMetadataCopyStrategy  # noqa: E402
from pylizlib.core.os.snap.copying.provider import _ProviderSnapshotCopyStrategy as _ProviderSnapshotCopyStrategy  # noqa: E402


class SequentialFileCopyStrategy(_SequentialFileCopyStrategy):
    """Copy files in sequence, preserving the library's current default."""

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
        """Copy to a new destination, recording/verifying content before success.

        Per-call counters live in a session; failures remove only this destination.

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
            NotADirectoryError: A required real directory is missing, is a link, or has another entry type.
            FileExistsError: A destination or generated staging name already exists or changes before publication.
            ValueError: A value, path, resource limit or metadata field violates the validation rules described above.
        """
        return super().copy_directory(source, destination, progress_callback, message_callback, manifest=manifest, expected_manifest=expected_manifest)


class VerifiedFileCopyStrategy(_VerifiedFileCopyStrategy):
    """Retry a sequential copy when a content-hash manifest changes.

    This detects changes visible between the pre-copy and post-copy scans and
    refuses to publish after repeated changes. It is not a filesystem snapshot:
    an ABA change or a writer coordinated with the scans can evade detection.
    Use ``ProviderSnapshotCopyStrategy`` for a source frozen by the filesystem,
    server, or application.

    Attributes:
        max_attempts (int): Positive retry count for source-fingerprint verification; non-integer and sub-one
            values are rejected.
        delegate (DirectoryCopyStrategy): Content-copy strategy retained by reference, preserving its consistency
            and callback contract.
    """

    def __init__(self, max_attempts: int = 3, delegate: DirectoryCopyStrategy | None = None):
        """Configure the attempt limit and delegate; keep the default sequential copier.

        Args:
            max_attempts (int): Positive retry count for source-fingerprint verification; non-integer and sub-one
                values are rejected.
            delegate (DirectoryCopyStrategy | None): Content-copy strategy retained by reference, preserving its
                consistency and callback contract.

        Returns:
            None: No return value.

        Raises:
            ValueError: A value, path, resource limit or metadata field violates the validation rules described above.
        """
        return super().__init__(max_attempts, delegate)

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
        """Publish only when source fingerprints agree before and after a copy.

        Retry source changes up to max_attempts; propagate other errors as before.

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
            SourceChangedError: Source fingerprints differ through every configured verified-copy attempt.
        """
        return super().copy_directory(source, destination, progress_callback, message_callback, manifest=manifest, expected_manifest=expected_manifest)


class ExtendedMetadataCopyStrategy(_ExtendedMetadataCopyStrategy):
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
        return super().__init__(delegate)

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
        return super().copy_directory(source, destination, progress_callback, message_callback, manifest=manifest, expected_manifest=expected_manifest)


class ProviderSnapshotCopyStrategy(_ProviderSnapshotCopyStrategy):
    """Copy from a stable tree supplied by a snapshot provider.

    The provider must either hold all writers quiesced for the context or yield
    an immutable filesystem/server snapshot. The strategy cannot enforce the
    provider's consistency guarantee itself.

    Attributes:
        provider (SourceSnapshotProvider): SourceSnapshotProvider supplying a stable tree for the full duration of
            its context.
        delegate (DirectoryCopyStrategy): Content-copy strategy retained by reference, preserving its consistency
            and callback contract.
    """

    def __init__(self, provider: SourceSnapshotProvider, delegate: DirectoryCopyStrategy | None = None):
        """Require the existing provider ABC and keep the supplied or default delegate.

        Args:
            provider (SourceSnapshotProvider): SourceSnapshotProvider supplying a stable tree for the full duration of
                its context.
            delegate (DirectoryCopyStrategy | None): Content-copy strategy retained by reference, preserving its
                consistency and callback contract.

        Returns:
            None: No return value.

        Raises:
            TypeError: An argument or mutable model field has a type rejected by this contract.
        """
        return super().__init__(provider, delegate)

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
        """Copy from the provider using the standard metadata policy.

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

        Notes:
            The provider context covers copying, any requested metadata work and the link check. Expected-manifest
            comparison and final destination publication occur afterward. The strategy cannot independently prove the
            provider's consistency guarantee.
        """
        return super().copy_directory(source, destination, progress_callback, message_callback, manifest=manifest, expected_manifest=expected_manifest)
