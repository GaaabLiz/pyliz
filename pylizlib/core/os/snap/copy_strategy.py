"""Pluggable strategies for copying snapshot directory trees."""

from __future__ import annotations

import errno
import hashlib
import os
import shutil
import stat
import tempfile
from abc import ABC, abstractmethod
from collections.abc import Mapping, MutableMapping
from enum import Enum
from pathlib import Path
from typing import ContextManager

from pylizlib.core.os.snap.callbacks import CopyProgressCallback as ProgressCallback
from pylizlib.core.os.snap.callbacks import MessageCallback
from pylizlib.core.os.snap.integrity import (
    IntegrityManifest,
    assert_manifest_matches,
    validate_integrity_manifest,
)
from pylizlib.core.os.snap.storage.tree import assert_destination_outside_source, assert_no_symlinks, is_link_or_junction, iter_tree_entries_strict


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
        """Copy a tree, optionally recording or validating its content manifest."""


def _remove_tree(path: Path) -> None:
    """Remove only the named entry, never follow a symlink at its root."""
    if path.is_symlink():
        path.unlink(missing_ok=True)
    elif path.exists():
        shutil.rmtree(path)


def _is_link_or_junction(path: Path) -> bool:
    """Compatibility helper for the common storage entry check."""
    return is_link_or_junction(path)


class _FileCopySession:
    """Per-call byte counters and manifest recording for sequential file copying.

    A strategy remains reusable: this mutable state belongs to one destination,
    not to the strategy instance or a process-wide default settings object.
    """

    def __init__(
        self, destination: Path, capture_integrity: bool, observed: IntegrityManifest | None, total_bytes: int, progress_callback: ProgressCallback | None, message_callback: MessageCallback | None
    ):
        """Capture the already-computed totals without performing additional I/O."""
        self.destination = destination
        self.capture_integrity = capture_integrity
        self.observed = observed
        self.total_bytes = total_bytes
        self.copied_bytes = 0
        self.progress_callback = progress_callback
        self.message_callback = message_callback

    def copy_file(self, src: str, dst: str, *, follow_symlinks: bool = True) -> str:
        """Copy and optionally hash exactly the bytes written, then report progress."""
        if self.message_callback:
            self.message_callback(f"Copia in corso: {Path(src).name}")
        if self.capture_integrity:
            digest = hashlib.sha256()
            file_size = 0
            with open(src, "rb") as source_file, open(dst, "xb") as destination_file:
                for chunk in iter(lambda: source_file.read(1024 * 1024), b""):
                    destination_file.write(chunk)
                    digest.update(chunk)
                    file_size += len(chunk)
            shutil.copystat(src, dst, follow_symlinks=follow_symlinks)
            relative_path = Path(dst).relative_to(self.destination).as_posix()
            assert self.observed is not None
            self.observed[relative_path] = {"type": "file", "size": file_size, "sha256": digest.hexdigest()}
            result = dst
        else:
            result = shutil.copy2(src, dst, follow_symlinks=follow_symlinks)
        if self.progress_callback:
            self.copied_bytes += Path(dst).stat().st_size
            self.progress_callback(self.copied_bytes, self.total_bytes)
        return result

    def record_directories(self) -> None:
        """Record stored directories, including empty ones, after file copying."""
        assert self.observed is not None

        def raise_walk_error(error: OSError) -> None:
            """Propagate a walk failure instead of treating an incomplete scan as success."""
            raise error

        for current, directories, _ in os.walk(self.destination, onerror=raise_walk_error):
            directories[:] = sorted(directories)
            for name in directories:
                relative_path = (Path(current) / name).relative_to(self.destination).as_posix()
                self.observed[relative_path] = {"type": "directory", "size": 0, "sha256": None}


class SequentialFileCopyStrategy(DirectoryCopyStrategy):
    """Copy files in sequence, preserving the library's current default."""

    @staticmethod
    def _total_bytes(source: Path) -> int:
        """Count source file bytes for progress, propagating walk and stat failures."""

        def raise_walk_error(error: OSError) -> None:
            """Propagate a walk failure instead of treating an incomplete scan as success."""
            raise error

        total = 0
        for current, directories, files in os.walk(source, onerror=raise_walk_error):
            # os.walk does not descend into symlink directories unless asked.
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

        Per-call counters live in a session; failures remove only this destination."""
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

        capture_integrity = manifest is not None or expected_manifest is not None
        if expected_manifest is not None:
            validate_integrity_manifest(dict(expected_manifest))
        observed: IntegrityManifest | None = {".": {"type": "directory", "size": 0, "sha256": None}} if capture_integrity else None
        total_bytes = self._total_bytes(source) if progress_callback else 0
        session = _FileCopySession(destination, capture_integrity, observed, total_bytes, progress_callback, message_callback)

        try:
            destination.mkdir()
            with os.scandir(source) as entries:
                for entry in entries:
                    source_item = Path(entry.path)
                    mode = entry.stat(follow_symlinks=False).st_mode
                    if stat.S_ISLNK(mode) or _is_link_or_junction(source_item):
                        raise ValueError(f"Directory copy does not accept symbolic links: '{source_item}'.")
                    destination_item = destination / entry.name
                    if stat.S_ISDIR(mode):
                        # Preserve a newly introduced link in staging rather
                        # than following it; the post-copy tree check rejects it.
                        shutil.copytree(source_item, destination_item, symlinks=True, copy_function=session.copy_file)
                    elif stat.S_ISREG(mode):
                        session.copy_file(str(source_item), str(destination_item))
                    else:
                        raise ValueError(f"Directory copy does not accept special file '{source_item}'.")
            assert_no_symlinks(destination)
            if capture_integrity:
                assert observed is not None

                session.record_directories()
                validate_integrity_manifest(observed)
                if expected_manifest is not None:
                    assert_manifest_matches(dict(expected_manifest), observed)
                if manifest is not None:
                    manifest.clear()
                    manifest.update(observed)
        except Exception:
            _remove_tree(destination)
            raise
        return destination


class ExtendedMetadataCopyStrategy(DirectoryCopyStrategy):
    """Decorate a copy strategy with strict, platform-supported metadata copying.

    The delegate continues to copy file contents and standard metadata. This
    strategy additionally restores the copied root directory metadata, owner
    and group where available, extended attributes (including Linux ACL
    attributes), Windows owner/group/DACL and alternate data streams, and
    hard-link relationships that exist within the copied tree. Unsupported
    metadata operations fail the copy instead of silently publishing a weaker
    result. Filesystem-specific metadata outside these APIs cannot be promised.
    """

    def __init__(self, delegate: DirectoryCopyStrategy):
        """Wrap one directory copy strategy without changing its content policy."""
        if not isinstance(delegate, DirectoryCopyStrategy):
            raise TypeError("delegate must implement DirectoryCopyStrategy.")
        self.delegate = delegate

    @staticmethod
    def _copy_extended_attributes(source: Path, destination: Path) -> None:
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

    @staticmethod
    def _copy_posix_owner_group(source: Path, destination: Path) -> None:
        """Copy POSIX ownership when the caller has the required privilege."""
        source_stat = source.stat(follow_symlinks=False)
        destination_stat = destination.stat(follow_symlinks=False)
        if (source_stat.st_uid, source_stat.st_gid) == (destination_stat.st_uid, destination_stat.st_gid):
            return
        chown = getattr(os, "chown", None)
        if chown is None:
            raise NotImplementedError("This platform cannot copy POSIX ownership.")
        chown(destination, source_stat.st_uid, source_stat.st_gid)

    @staticmethod
    def _copy_windows_security(source: Path, destination: Path) -> None:
        """Copy the Windows owner, group and discretionary access control list."""
        try:
            import win32security
        except ImportError as error:
            raise NotImplementedError("Extended Windows security copying requires pywin32.") from error

        security_information = (
            win32security.OWNER_SECURITY_INFORMATION
            | win32security.GROUP_SECURITY_INFORMATION
            | win32security.DACL_SECURITY_INFORMATION
        )
        descriptor = win32security.GetFileSecurity(str(source), security_information)
        win32security.SetFileSecurity(str(destination), security_information, descriptor)

    @staticmethod
    def _copy_windows_streams(source: Path, destination: Path) -> None:
        """Copy NTFS alternate data streams exposed by FindFirstStreamW."""
        import ctypes
        from ctypes import wintypes

        class FindStreamData(ctypes.Structure):
            """Win32 stream enumeration result layout."""

            _fields_ = [("stream_size", ctypes.c_longlong), ("stream_name", wintypes.WCHAR * 296)]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        find_first = kernel32.FindFirstStreamW
        find_first.argtypes = [wintypes.LPCWSTR, ctypes.c_int, ctypes.POINTER(FindStreamData), wintypes.DWORD]
        find_first.restype = wintypes.HANDLE
        find_next = kernel32.FindNextStreamW
        find_next.argtypes = [wintypes.HANDLE, ctypes.POINTER(FindStreamData)]
        find_next.restype = wintypes.BOOL
        find_close = kernel32.FindClose
        find_close.argtypes = [wintypes.HANDLE]
        find_close.restype = wintypes.BOOL

        stream_data = FindStreamData()
        handle = find_first(str(source), 0, ctypes.byref(stream_data), 0)
        invalid_handle = ctypes.c_void_p(-1).value
        if handle == invalid_handle:
            error_code = ctypes.get_last_error()
            # These filesystems expose no alternate data streams.
            if error_code in (1, 38, 50):
                return
            raise ctypes.WinError(error_code)

        try:
            while True:
                stream_name = stream_data.stream_name
                if stream_name != "::$DATA" and stream_name.endswith(":$DATA"):
                    stream_suffix = stream_name[:-6]
                    with open(f"{source}{stream_suffix}", "rb") as input_stream:
                        with open(f"{destination}{stream_suffix}", "wb") as output_stream:
                            shutil.copyfileobj(input_stream, output_stream)
                if not find_next(handle, ctypes.byref(stream_data)):
                    error_code = ctypes.get_last_error()
                    if error_code != 38:  # ERROR_HANDLE_EOF
                        raise ctypes.WinError(error_code)
                    break
        finally:
            find_close(handle)

    @classmethod
    def _preserve_metadata(cls, source: Path, destination: Path) -> None:
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
                cls._copy_windows_streams(source_path, destination_path)
            else:
                cls._copy_posix_owner_group(source_path, destination_path)
            # Ownership changes can clear set-id or capability bits.
            shutil.copystat(source_path, destination_path, follow_symlinks=False)
            if os.name != "nt":
                # Apply ACL xattrs after copystat because chmod can adjust ACL masks.
                cls._copy_extended_attributes(source_path, destination_path)

        if os.name == "nt":
            # DACLs are applied last because a source ACL can deny the current
            # process access needed to finish metadata updates on the staging tree.
            for source_path, destination_path in ordered_entries:
                cls._copy_windows_security(source_path, destination_path)

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
        """Stage the delegate copy, enrich metadata, then publish it as a unit."""
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
            provider_delegate = isinstance(self.delegate, ProviderSnapshotCopyStrategy)
            if provider_delegate:
                self.delegate._copy_directory_with_metadata_mode(
                    source,
                    staged,
                    progress_callback,
                    message_callback,
                    manifest=staged_manifest,
                    expected_manifest=expected_manifest,
                    copy_metadata_mode=CopyMetadataMode.EXTENDED,
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
            if not provider_delegate:
                self._preserve_metadata(source, staged)
            if destination.exists() or destination.is_symlink():
                raise FileExistsError(f"Copy destination '{destination}' was created during copying.")
            staged.rename(destination)
            if manifest is not None:
                manifest.clear()
                manifest.update(staged_manifest or {})
        return destination


class VerifiedFileCopyStrategy(DirectoryCopyStrategy):
    """Retry a sequential copy when a content-hash manifest changes.

    This detects changes visible between the pre-copy and post-copy scans and
    refuses to publish after repeated changes. It is not a filesystem snapshot:
    an ABA change or a writer coordinated with the scans can evade detection.
    Use ``ProviderSnapshotCopyStrategy`` for a source frozen by the filesystem,
    server, or application.
    """

    def __init__(self, max_attempts: int = 3, delegate: DirectoryCopyStrategy | None = None):
        """Configure the attempt limit and delegate; keep the default sequential copier."""
        if type(max_attempts) is not int or max_attempts < 1:
            raise ValueError("max_attempts must be a positive integer.")
        self.max_attempts = max_attempts
        self.delegate = delegate or SequentialFileCopyStrategy()

    @staticmethod
    def _manifest(root: Path) -> dict[str, tuple[str, int | str]]:
        """Fingerprint source files and directories, rejecting links and special files.

        This scan representation is distinct from the persisted integrity manifest."""
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

        Retry source changes up to max_attempts; propagate other errors as before."""
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


class SourceSnapshotProvider(ABC):
    """Adapter for a filesystem, server, or application snapshot facility."""

    @abstractmethod
    def create_snapshot(self, source: Path) -> ContextManager[Path]:
        """Yield a stable point-in-time directory for ``source``."""


class ProviderSnapshotCopyStrategy(DirectoryCopyStrategy):
    """Copy from a stable tree supplied by a snapshot provider.

    The provider must either hold all writers quiesced for the context or yield
    an immutable filesystem/server snapshot. The strategy cannot enforce the
    provider's consistency guarantee itself.
    """

    def __init__(self, provider: SourceSnapshotProvider, delegate: DirectoryCopyStrategy | None = None):
        """Require the existing provider ABC and keep the supplied or default delegate."""
        if not isinstance(provider, SourceSnapshotProvider):
            raise TypeError("provider must implement SourceSnapshotProvider.")
        self.provider = provider
        self.delegate = delegate or SequentialFileCopyStrategy()

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
        """Copy from the provider using the standard metadata policy."""
        return self._copy_directory_with_metadata_mode(
            source,
            destination,
            progress_callback,
            message_callback,
            manifest=manifest,
            expected_manifest=expected_manifest,
            copy_metadata_mode=CopyMetadataMode.BASIC,
        )

    def _copy_directory_with_metadata_mode(
        self,
        source: Path,
        destination: Path,
        progress_callback: ProgressCallback | None = None,
        message_callback: MessageCallback | None = None,
        *,
        manifest: MutableMapping[str, dict[str, str | int | None]] | None = None,
        expected_manifest: Mapping[str, dict[str, str | int | None]] | None = None,
        copy_metadata_mode: CopyMetadataMode = CopyMetadataMode.BASIC,
    ) -> Path:
        """Copy within the provider context, then verify and publish the staged tree.

        The output manifest is updated only after successful publication. Extended
        metadata is read from the provider's stable tree, not the live source."""
        if not isinstance(copy_metadata_mode, CopyMetadataMode):
            raise TypeError("copy_metadata_mode must be a CopyMetadataMode.")
        destination = Path(destination)
        if destination.exists() or destination.is_symlink():
            raise FileExistsError(f"Copy destination '{destination}' already exists.")
        assert_no_symlinks(Path(source))
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".provider_copy_", dir=destination.parent) as temporary_directory:
            staged = Path(temporary_directory) / "copy"
            observed: IntegrityManifest | None = {} if manifest is not None or expected_manifest is not None else None
            self._copy_from_provider(source, staged, progress_callback, message_callback, observed, copy_metadata_mode)
            if expected_manifest is not None:
                assert_manifest_matches(dict(expected_manifest), observed or {})
            if destination.exists() or destination.is_symlink():
                raise FileExistsError(f"Copy destination '{destination}' was created during copying.")
            staged.rename(destination)
            if manifest is not None:
                manifest.clear()
                manifest.update(observed or {})
        return destination

    def _copy_from_provider(
        self,
        source: Path,
        destination: Path,
        progress_callback: ProgressCallback | None,
        message_callback: MessageCallback | None,
        observed_manifest: MutableMapping[str, dict[str, str | int | None]] | None,
        copy_metadata_mode: CopyMetadataMode,
    ) -> Path:
        """Copy only while the provider context holds its stable source available."""
        with self.provider.create_snapshot(Path(source)) as stable_source:
            stable_source = Path(stable_source)
            if _is_link_or_junction(stable_source) or not stable_source.is_dir():
                raise NotADirectoryError(f"Snapshot provider returned invalid source '{stable_source}'.")
            assert_no_symlinks(stable_source)
            if observed_manifest is None:
                copied = self.delegate.copy_directory(stable_source, destination, progress_callback, message_callback)
            else:
                copied = self.delegate.copy_directory(
                    stable_source,
                    destination,
                    progress_callback,
                    message_callback,
                    manifest=observed_manifest,
                )
            if copy_metadata_mode is CopyMetadataMode.EXTENDED:
                ExtendedMetadataCopyStrategy._preserve_metadata(stable_source, copied)
            assert_no_symlinks(copied)
            return copied
