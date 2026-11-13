"""Coordinate provider-owned source lifetime, staging and manifest publication."""

from __future__ import annotations

import tempfile
from collections.abc import Mapping, MutableMapping
from pathlib import Path

from pylizlib.core.os.snap.callbacks import CopyProgressCallback, MessageCallback
from pylizlib.core.os.snap.callbacks import CopyProgressCallback as ProgressCallback
from pylizlib.core.os.snap.copy_strategy import DirectoryCopyStrategy, SourceSnapshotProvider
from pylizlib.core.os.snap.copying.contracts import MetadataCopier
from pylizlib.core.os.snap.integrity import IntegrityManifest, assert_manifest_matches
from pylizlib.core.os.snap.storage.tree import assert_no_symlinks, is_link_or_junction


class ProviderCopySession:
    """Keep source consistency independent of the content and metadata policies.

    Attributes:
        provider (SourceSnapshotProvider): SourceSnapshotProvider supplying a stable tree for the full duration of
            its context.
        delegate (DirectoryCopyStrategy): Content-copy strategy retained by reference, preserving its consistency
            and callback contract.
    """

    def __init__(self, provider: SourceSnapshotProvider, delegate: DirectoryCopyStrategy):
        """Retain a validated provider and content-copy strategy.

        Args:
            provider (SourceSnapshotProvider): Owner of the stable-source context.
            delegate (DirectoryCopyStrategy): Strategy copying from that stable tree.

        Returns:
            None: The source context is acquired only when copy is called.
        """
        self.provider = provider
        self.delegate = delegate

    def copy(
        self,
        source: Path,
        destination: Path,
        progress_callback: CopyProgressCallback | None = None,
        message_callback: MessageCallback | None = None,
        *,
        metadata_copier: MetadataCopier | None = None,
        manifest: MutableMapping[str, dict[str, str | int | None]] | None = None,
        expected_manifest: Mapping[str, dict[str, str | int | None]] | None = None,
    ) -> Path:
        """Stage a stable-source copy, verify content and publish the completed tree.

        Args:
            source (Path): Source file or directory whose contents or metadata are read.
            destination (Path): Target path receiving the copied content or metadata.
            progress_callback (CopyProgressCallback | None): Optional observer receiving (copied_bytes, total_bytes),
                including terminal empty-tree progress; return values do not cancel copying.
            message_callback (MessageCallback | None): Optional status observer receiving one message string; its
                exceptions propagate according to the calling operation.
            metadata_copier (MetadataCopier | None): Optional hook receiving actual stable source and copied staging
                tree before that source context closes.
            manifest (MutableMapping[str, dict[str, str | int | None]] | None): Optional mutable captured-integrity
                output, replaced only on successful copy. expected_manifest can still require verification when this
                is None.
            expected_manifest (Mapping[str, dict[str, str | int | None]] | None): Previously captured integrity
                mapping to verify before publishing; None disables this comparison.

        Returns:
            Path: Stage a stable-source copy, verify content and publish the completed tree.

        Raises:
            FileExistsError: A destination or generated staging name already exists or changes before publication.
        """
        destination = Path(destination)
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(f"Copy destination '{destination}' already exists.")
        assert_no_symlinks(Path(source))
        destination.parent.mkdir(parents=True, exist_ok=True)

        # Staging is owned by this invocation; failed copies never publish a manifest.
        with tempfile.TemporaryDirectory(prefix=".provider_copy_", dir=destination.parent) as temporary_directory:
            staged = Path(temporary_directory) / "copy"
            observed: IntegrityManifest | None = {} if manifest is not None or expected_manifest is not None else None
            self._copy_stable_tree(source, staged, progress_callback, message_callback, observed, metadata_copier)
            if expected_manifest is not None:
                assert_manifest_matches(dict(expected_manifest), observed or {})
            if destination.exists() or destination.is_symlink():
                raise FileExistsError(f"Copy destination '{destination}' was created during copying.")
            staged.rename(destination)
            if manifest is not None:
                manifest.clear()
                manifest.update(observed or {})
        return destination

    def _copy_stable_tree(
        self,
        source: Path,
        destination: Path,
        progress_callback: CopyProgressCallback | None,
        message_callback: MessageCallback | None,
        observed_manifest: MutableMapping[str, dict[str, str | int | None]] | None,
        metadata_copier: MetadataCopier | None,
    ) -> Path:
        """Complete contents and metadata before the provider releases its source.

        Args:
            source (Path): Source file or directory whose contents or metadata are read.
            destination (Path): Target path receiving the copied content or metadata.
            progress_callback (CopyProgressCallback | None): Optional observer receiving (copied_bytes, total_bytes),
                including terminal empty-tree progress; return values do not cancel copying.
            message_callback (MessageCallback | None): Optional status observer receiving one message string; its
                exceptions propagate according to the calling operation.
            observed_manifest (MutableMapping[str, dict[str, str | int | None]] | None): Integrity output for this
                copy attempt, or None to preserve legacy delegates without manifest kwargs.
            metadata_copier (MetadataCopier | None): Optional hook receiving actual stable source and copied staging
                tree before that source context closes.

        Returns:
            Path: Completed staging destination after content, metadata and link checks; the provider context exits
                before control returns.

        Raises:
            NotADirectoryError: A required real directory is missing, is a link, or has another entry type.
        """
        with self.provider.create_snapshot(Path(source)) as stable_source:
            stable_source = Path(stable_source)
            if is_link_or_junction(stable_source) or not stable_source.is_dir():
                raise NotADirectoryError(f"Snapshot provider returned invalid source '{stable_source}'.")
            assert_no_symlinks(stable_source)

            # Preserve legacy four-positional-argument delegates when no manifest is needed.
            if observed_manifest is None:
                copied = self.delegate.copy_directory(stable_source, destination, progress_callback, message_callback)
            else:
                copied = self.delegate.copy_directory(stable_source, destination, progress_callback, message_callback, manifest=observed_manifest)
            if metadata_copier is not None:
                metadata_copier(stable_source, copied)
            assert_no_symlinks(copied)
            return copied


class _ProviderSnapshotCopyStrategy(DirectoryCopyStrategy):
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
        if not isinstance(provider, SourceSnapshotProvider):
            raise TypeError("provider must implement SourceSnapshotProvider.")
        self.provider = provider
        if delegate is None:
            from pylizlib.core.os.snap.copy_strategy import SequentialFileCopyStrategy

            delegate = SequentialFileCopyStrategy()
        self.delegate = delegate

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
        return ProviderCopySession(self.provider, self.delegate).copy(source, destination, progress_callback, message_callback, manifest=manifest, expected_manifest=expected_manifest)

    def copy_directory_with_metadata(
        self,
        source: Path,
        destination: Path,
        progress_callback: ProgressCallback | None = None,
        message_callback: MessageCallback | None = None,
        *,
        metadata_copier: MetadataCopier,
        manifest: MutableMapping[str, dict[str, str | int | None]] | None = None,
        expected_manifest: Mapping[str, dict[str, str | int | None]] | None = None,
    ) -> Path:
        """Apply the supplied metadata hook while the provider's source stays valid.

        Args:
            source (Path): Source file or directory whose contents or metadata are read.
            destination (Path): Target path receiving the copied content or metadata.
            progress_callback (ProgressCallback | None): Optional observer receiving (copied_bytes, total_bytes),
                including terminal empty-tree progress; return values do not cancel copying.
            message_callback (MessageCallback | None): Optional status observer receiving one message string; its
                exceptions propagate according to the calling operation.
            metadata_copier (MetadataCopier): Optional hook receiving actual stable source and copied staging tree
                before that source context closes.
            manifest (MutableMapping[str, dict[str, str | int | None]] | None): Optional mutable captured-integrity
                output, replaced only on successful copy. expected_manifest can still require verification when this
                is None.
            expected_manifest (Mapping[str, dict[str, str | int | None]] | None): Previously captured integrity
                mapping to verify before publishing; None disables this comparison.

        Returns:
            Path: Final destination after the metadata hook completed while the actual stable source was still
                available.
        """
        return ProviderCopySession(self.provider, self.delegate).copy(
            source, destination, progress_callback, message_callback, metadata_copier=metadata_copier, manifest=manifest, expected_manifest=expected_manifest
        )
