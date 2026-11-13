"""Sequential and verified strategies for copying directory trees."""

from __future__ import annotations

import os
import shutil
import stat
import tempfile
from collections.abc import Mapping, MutableMapping
from pathlib import Path

from pylizlib.core.os.filesystem.fingerprints import fingerprint_tree
from pylizlib.core.os.snap.callbacks import CopyProgressCallback as ProgressCallback
from pylizlib.core.os.snap.callbacks import MessageCallback
from pylizlib.core.os.snap.copy_strategy import DirectoryCopyStrategy, SourceChangedError, _is_link_or_junction, _remove_tree
from pylizlib.core.os.snap.copying.session import _FileCopySession
from pylizlib.core.os.snap.integrity import IntegrityManifest, assert_manifest_matches, validate_integrity_manifest
from pylizlib.core.os.snap.storage.tree import assert_no_symlinks


class _SequentialFileCopyStrategy(DirectoryCopyStrategy):
    """Copy files in sequence, preserving the library's current default."""

    @staticmethod
    def _total_bytes(source: Path) -> int:
        """Count source file bytes for progress, propagating walk and stat failures.

        Args:
            source (Path): Source file or directory whose contents or metadata are read.

        Returns:
            int: Sum of file byte sizes used as a progress estimate; scanning errors are not ignored.
        """

        def raise_walk_error(error: OSError) -> None:
            """Propagate a walk failure instead of treating an incomplete scan as success.

            Args:
                error (OSError): Original failure to propagate or preserve as the cause of a rollback failure.

            Returns:
                None: No return value.
            """
            raise error

        total = 0

        # os.walk does not descend into symlink directories unless asked.
        for current, directories, files in os.walk(source, onerror=raise_walk_error):
            directories[:] = [name for name in directories if not (Path(current) / name).is_symlink()]
            for name in files:
                total += (Path(current) / name).stat().st_size
        return total

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

        # Validate source and destination before creating any owned staging entry.
        source = Path(source)
        destination = Path(destination)
        if not source.is_dir():
            raise NotADirectoryError(f"Copy source '{source}' is not a directory.")
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(f"Copy destination '{destination}' already exists.")

        # Fail before creating staging if any link, including a dangling one,
        # could be followed by the copy operation.
        assert_no_symlinks(source)
        destination.parent.mkdir(parents=True, exist_ok=True)

        # Hash only when requested; scan byte totals only for an active progress observer.
        capture_integrity = manifest is not None or expected_manifest is not None
        if expected_manifest is not None:
            validate_integrity_manifest(dict(expected_manifest))
        observed: IntegrityManifest | None = {".": {"type": "directory", "size": 0, "sha256": None}} if capture_integrity else None
        total_bytes = self._total_bytes(source) if progress_callback else 0
        session = _FileCopySession(destination, capture_integrity, observed, total_bytes, progress_callback, message_callback)

        # The destination belongs to this call and is removed if any copy phase fails.
        try:
            destination.mkdir()
            with os.scandir(source) as entries:
                for entry in entries:
                    source_item = Path(entry.path)
                    mode = entry.stat(follow_symlinks=False).st_mode
                    if stat.S_ISLNK(mode) or _is_link_or_junction(source_item):
                        raise ValueError(f"Directory copy does not accept symbolic links: '{source_item}'.")
                    destination_item = destination / entry.name

                    # Preserve a newly introduced link in staging rather
                    # than following it; the post-copy tree check rejects it.
                    if stat.S_ISDIR(mode):
                        shutil.copytree(source_item, destination_item, symlinks=True, copy_function=session.copy_file)
                    elif stat.S_ISREG(mode):
                        session.copy_file(str(source_item), str(destination_item))
                    else:
                        raise ValueError(f"Directory copy does not accept special file '{source_item}'.")

            # Reject links introduced during copying before validating or returning content.
            assert_no_symlinks(destination)
            if capture_integrity:
                assert observed is not None

                session.record_directories()
                validate_integrity_manifest(observed)
                if expected_manifest is not None:
                    assert_manifest_matches(dict(expected_manifest), observed)
            session.finish()
            if capture_integrity and manifest is not None:
                assert observed is not None
                manifest.clear()
                manifest.update(observed)
        except Exception:
            _remove_tree(destination)
            raise
        return destination


class _VerifiedFileCopyStrategy(DirectoryCopyStrategy):
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
        if type(max_attempts) is not int or max_attempts < 1:
            raise ValueError("max_attempts must be a positive integer.")
        self.max_attempts = max_attempts
        if delegate:
            self.delegate = delegate
        else:
            from pylizlib.core.os.snap.copy_strategy import SequentialFileCopyStrategy

            self.delegate = SequentialFileCopyStrategy()

    @staticmethod
    def _manifest(root: Path) -> dict[str, tuple[str, int | str]]:
        """Fingerprint source files and directories, rejecting links and special files.

        This scan representation is distinct from the persisted integrity manifest.

        Args:
            root (Path): Root directory for the tree operation; link and existence policy is described above.

        Returns:
            dict[str, tuple[str, int | str]]: Relative path fingerprint: directories map to (directory, 0), files to
                (SHA-256 hex digest, byte size).
        """
        return fingerprint_tree(root)

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
        source = Path(source)
        destination = Path(destination)
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(f"Copy destination '{destination}' already exists.")
        destination.parent.mkdir(parents=True, exist_ok=True)

        for attempt in range(1, self.max_attempts + 1):
            before = self._manifest(source)
            with tempfile.TemporaryDirectory(prefix=".verified_copy_", dir=destination.parent) as temporary_directory:
                staged = Path(temporary_directory) / "copy"
                attempt_manifest: IntegrityManifest | None = {} if manifest is not None or expected_manifest is not None else None
                if attempt_manifest is None:
                    self.delegate.copy_directory(source, staged, progress_callback, message_callback)
                else:
                    self.delegate.copy_directory(source, staged, progress_callback, message_callback, manifest=attempt_manifest)
                after = self._manifest(source)
                if before == after:
                    if expected_manifest is not None:
                        assert_manifest_matches(dict(expected_manifest), attempt_manifest or {})
                    if destination.exists() or destination.is_symlink():
                        raise FileExistsError(f"Copy destination '{destination}' was created during copying.")
                    assert_no_symlinks(staged)
                    staged.rename(destination)
                    if manifest is not None:
                        manifest.clear()
                        manifest.update(attempt_manifest or {})
                    return destination
            if attempt < self.max_attempts and message_callback:
                message_callback(f"Sorgente modificata durante la copia; nuovo tentativo {attempt + 1}/{self.max_attempts}.")

        raise SourceChangedError(f"Source '{source}' changed during all {self.max_attempts} copy attempts.")
