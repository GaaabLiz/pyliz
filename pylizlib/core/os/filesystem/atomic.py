"""Protected descriptor access and same-directory atomic file publication.

The previous version is retained in a hidden sidecar. Directory flushing is
best effort on unsupported platforms; a remote server acknowledging fsync does
not prove that the data reached physical media.
"""

import errno
import os
import secrets
import stat
from collections.abc import Callable
from pathlib import Path

from pylizlib.core.log.pylizLogger import logger
from pylizlib.core.os.filesystem.tree import is_link_or_junction


class FileDurabilityError(OSError):
    """Report successful name publication followed by an unconfirmed directory flush.

    Attributes:
        path (Path): File whose new name has already been published.
        published (bool): Always True: callers must not assume publication failed.
        durability_confirmed (bool): Always False: the final flush raised an error.
    """

    def __init__(self, path: Path, cause: OSError, *, subject: str = "File"):
        """Store publication outcome while the caller chains the underlying cause.

        Args:
            path (Path): Already-published destination.
            cause (OSError): Final directory-sync failure, included in the message.
            subject (str): Human-readable subject of the error message.

        Returns:
            None: The exception stores the path and publication flags.
        """
        super().__init__(f"{subject} '{path}' was published atomically, but storage durability could not be confirmed: {cause}")
        self.path = Path(path)
        self.published = True
        self.durability_confirmed = False


class AtomicFile:
    """Read regular files safely and publish writes through same-directory staging.

    Successful writes fsync the staged file before atomically replacing the
    current name, and retain the previous bytes in a hidden sidecar. Parent
    directory fsync is attempted where supported. A successful fsync request
    cannot prove that a remote server has committed data to stable media.

    Attributes:
        path_label (str): Subject used in path-validation errors, customizable by adapters.
        temporary_label (str): Subject used for invalid staging entries.
        contents_label (str): Subject used when rejecting non-byte contents.
        durability_error (type[OSError]): Exception constructed after a published
            replacement whose final directory flush fails.
    """

    path_label = "File"
    temporary_label = "Temporary file"
    contents_label = "File"
    durability_error = FileDurabilityError

    _UNSUPPORTED_DIRECTORY_SYNC = {
        errno.EBADF,
        errno.EINVAL,
        getattr(errno, "ENOTSUP", errno.EINVAL),
        getattr(errno, "EOPNOTSUPP", errno.EINVAL),
    }

    @classmethod
    def previous_path(cls, path: Path) -> Path:
        """Compute the hidden sibling holding the prior published version.

        Args:
            path (Path): Destination file, not required to exist.

        Returns:
            Path: Sibling named ``.<filename>.previous``; no I/O is performed.
        """
        path = Path(path)
        return path.with_name(f".{path.name}.previous")

    @classmethod
    def open_file(cls, path: Path, flags: int, mode: int = 0o666) -> int:
        """Open a file with parent-identity checks and link rejection.

        Args:
            path (Path): File below an existing real parent directory.
            flags (int): Native os.open flags; O_NOFOLLOW is added when available.
            mode (int): Creation permissions, filtered by umask where applicable.

        Returns:
            int: Open descriptor owned by the caller, who must close it.

        Raises:
            ValueError: If the parent or entry is unsafe or changes during opening.
            OSError: If opening or inspecting an entry fails.
        """
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        directory = getattr(os, "O_DIRECTORY", 0)
        parent_before = path.parent.lstat()
        if not stat.S_ISDIR(parent_before.st_mode) or is_link_or_junction(path.parent):
            raise ValueError(f"{cls.path_label} directory '{path.parent}' is not a real directory.")

        if nofollow and directory and os.open in os.supports_dir_fd:
            parent_fd = os.open(path.parent, os.O_RDONLY | directory | nofollow)
            try:
                if not os.path.samestat(parent_before, os.fstat(parent_fd)):
                    raise ValueError(f"{cls.path_label} directory '{path.parent}' changed while opening it.")
                return os.open(path.name, flags | nofollow, mode, dir_fd=parent_fd)
            finally:
                os.close(parent_fd)

        try:
            file_before = path.lstat()
        except FileNotFoundError:
            file_before = None
        if file_before is not None and (not stat.S_ISREG(file_before.st_mode) or is_link_or_junction(path)):
            raise ValueError(f"{cls.path_label} path '{path}' cannot be a symbolic link.")

        descriptor = os.open(path, flags | nofollow, mode)
        try:
            parent_after = path.parent.lstat()
            file_after = path.lstat()
            opened_file = os.fstat(descriptor)
            if not stat.S_ISDIR(parent_after.st_mode) or is_link_or_junction(path.parent) or not os.path.samestat(parent_before, parent_after):
                raise ValueError(f"{cls.path_label} directory '{path.parent}' changed while opening it.")
            if not stat.S_ISREG(opened_file.st_mode) or not os.path.samestat(opened_file, file_after) or (file_before is not None and not os.path.samestat(file_before, file_after)):
                raise ValueError(f"{cls.path_label} path '{path}' changed while opening it.")
            return descriptor
        except Exception:
            os.close(descriptor)
            raise

    @classmethod
    def read_bytes(cls, path: Path, opener: Callable = None) -> bytes:
        """Read all bytes from a checked regular file and close its descriptor.

        Args:
            path (Path): Existing regular file below a real parent.
            opener (Callable | None): Protected open hook accepting path and flags,
                or the class open_file implementation when omitted.

        Returns:
            bytes: Entire file contents without decoding or newline conversion.

        Raises:
            ValueError: If the opened descriptor is not a regular file.
            OSError: If opening, reading or closing fails.
        """
        descriptor = (opener if opener is not None else cls.open_file)(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise ValueError(f"{cls.path_label} path '{path}' is not a regular file.")
            with os.fdopen(descriptor, "rb", closefd=False) as file:
                return file.read()
        finally:
            os.close(descriptor)

    @classmethod
    def _regular_file_stat(cls, path: Path) -> os.stat_result | None:
        """Inspect a file entry without following links.

        Args:
            path (Path): Entry whose absence is permitted.

        Returns:
            os.stat_result | None: lstat data for a regular file, or None if absent.

        Raises:
            ValueError: If an existing entry is a link, junction or non-regular file.
            OSError: If inspection fails for another reason.
        """
        try:
            file_stat = path.lstat()
        except FileNotFoundError:
            return None
        if not stat.S_ISREG(file_stat.st_mode) or is_link_or_junction(path):
            raise ValueError(f"{cls.path_label} path '{path}' must be a regular file.")
        return file_stat

    @classmethod
    def _temporary_path(cls, path: Path) -> Path:
        """Choose an unpredictable sibling staging name without creating it.

        Args:
            path (Path): Destination determining the staging parent and basename.

        Returns:
            Path: Hidden sibling ending in .tmp; exclusive creation is still required.
        """
        return path.with_name(f".{path.name}.{secrets.token_hex(12)}.tmp")

    @classmethod
    def _write_temporary(cls, path: Path, contents: bytes, opener: Callable, mode: int, *, preserve_mode: bool) -> None:
        """Create exclusively, write and fsync one staging file.

        Args:
            path (Path): Uncreated temporary sibling.
            contents (bytes): Complete bytes to write without transformation.
            opener (Callable): Protected open hook accepting path, flags and mode.
            mode (int): Creation mode and optional permissions to preserve.
            preserve_mode (bool): Apply fchmod on supported non-Windows platforms.

        Returns:
            None: After file flush/fsync and descriptor close.

        Raises:
            ValueError: If the created descriptor is not regular.
            OSError: If creation, permissions, write, short-write detection or sync fails.
        """
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NONBLOCK", 0)
        descriptor = opener(path, flags, mode)
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise ValueError(f"{cls.temporary_label} path '{path}' is not a regular file.")
            if preserve_mode and os.name != "nt" and hasattr(os, "fchmod"):
                os.fchmod(descriptor, mode)
            with os.fdopen(descriptor, "wb", closefd=False) as file:
                written = file.write(contents)
                if written != len(contents):
                    raise OSError(f"Short write while preparing metadata '{path}'.")
                file.flush()
                os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @classmethod
    def _same_parent(cls, path: Path, expected: os.stat_result) -> bool:
        """Compare a destination's current parent with its previously observed identity.

        Args:
            path (Path): File whose parent is inspected with lstat.
            expected (os.stat_result): Parent stat captured before staging.

        Returns:
            bool: Whether the parent is still the same real directory.

        Raises:
            OSError: If inspecting the parent fails.
        """
        current = path.parent.lstat()
        return stat.S_ISDIR(current.st_mode) and not is_link_or_junction(path.parent) and os.path.samestat(expected, current)

    @classmethod
    def _replace_sibling(cls, source: Path, destination: Path, expected_parent: os.stat_result) -> None:
        """Replace a sibling using a checked parent descriptor where supported.

        Args:
            source (Path): Prepared sibling file consumed by successful replacement.
            destination (Path): Entry to publish in the same parent directory.
            expected_parent (os.stat_result): Parent identity observed before staging.

        Returns:
            None: Once the name has been replaced; no durability flush is done here.

        Raises:
            ValueError: If the parent identity changed before publication.
            OSError: If checking, replacing or closing the parent descriptor fails.
        """
        if not cls._same_parent(destination, expected_parent):
            raise ValueError(f"{cls.path_label} directory '{destination.parent}' changed before publication.")

        directory_flag = getattr(os, "O_DIRECTORY", 0)
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        if directory_flag and os.replace in os.supports_dir_fd:
            parent_fd = os.open(destination.parent, os.O_RDONLY | directory_flag | nofollow)
            try:
                if not os.path.samestat(expected_parent, os.fstat(parent_fd)):
                    raise ValueError(f"{cls.path_label} directory '{destination.parent}' changed before publication.")
                os.replace(source.name, destination.name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
            finally:
                os.close(parent_fd)
        else:
            os.replace(source, destination)

    @classmethod
    def _sync_parent_directory(cls, path: Path, expected_parent: os.stat_result) -> bool:
        """Flush a destination's parent after verifying the expected directory identity.

        Args:
            path (Path): File whose parent namespace should be flushed.
            expected_parent (os.stat_result): Parent identity observed before staging.

        Returns:
            bool: True after successful fsync; False for unsupported directory sync.

        Raises:
            OSError: If the parent changed or a supported sync/open operation fails.
        """
        directory_flag = getattr(os, "O_DIRECTORY", 0)
        if not directory_flag:
            return False

        try:
            parent_fd = os.open(path.parent, os.O_RDONLY | directory_flag | getattr(os, "O_NOFOLLOW", 0))
        except OSError as error:
            if os.name == "nt" or error.errno in cls._UNSUPPORTED_DIRECTORY_SYNC:
                return False
            raise

        try:
            if not os.path.samestat(expected_parent, os.fstat(parent_fd)):
                raise OSError(f"{cls.path_label} directory '{path.parent}' changed before directory sync.")
            try:
                os.fsync(parent_fd)
            except OSError as error:
                if error.errno in cls._UNSUPPORTED_DIRECTORY_SYNC:
                    return False
                raise
            return True
        finally:
            os.close(parent_fd)

    @classmethod
    def write_bytes(cls, path: Path, contents: bytes, opener: Callable = None) -> None:
        """Atomically replace a regular metadata file and preserve its prior bytes.

        The temporary and previous-version files are created beside ``path``.
        Errors before replacing ``path`` leave the current version untouched.
        A :class:`FileDurabilityError` means replacement succeeded but the
        final parent-directory fsync failed. Network servers may acknowledge
        flushes without guaranteeing physical-media persistence.

        Args:
            path (Path): Absent or regular destination below an existing real parent.
            contents (bytes): Complete new version; non-byte values are rejected
                using isinstance(contents, bytes).
            opener (Callable | None): Optional protected-open hook accepting path,
                flags and mode; the class open_file is used when omitted.

        Returns:
            None: After publication; unsupported directory flushing is logged.

        Raises:
            TypeError: If contents is not bytes.
            ValueError: If the destination, previous sidecar or parent is unsafe.
            FileDurabilityError: If publication succeeds but the final flush fails.
                An adapter may configure a compatible OSError type.
            OSError: If inspection, staging, prior-version publication or replace fails.
        """
        path = Path(path)
        if not isinstance(contents, bytes):
            raise TypeError(f"{cls.contents_label} contents must be bytes.")
        opener = opener if opener is not None else cls.open_file
        parent_stat = path.parent.lstat()
        if not stat.S_ISDIR(parent_stat.st_mode) or is_link_or_junction(path.parent):
            raise ValueError(f"{cls.path_label} directory '{path.parent}' is not a real directory.")

        current_stat = cls._regular_file_stat(path)
        previous_bytes = None
        if current_stat is not None:
            previous_bytes = cls._read_previous_version(path, current_stat, opener)

        previous_path = cls.previous_path(path)
        cls._regular_file_stat(previous_path)
        new_temp = cls._temporary_path(path)
        previous_temp = cls._temporary_path(previous_path) if previous_bytes is not None else None
        try:
            file_mode = stat.S_IMODE(current_stat.st_mode) if current_stat is not None else 0o666
            cls._write_temporary(new_temp, contents, opener, file_mode, preserve_mode=current_stat is not None)

            if previous_bytes is not None:
                previous_mode = stat.S_IMODE(current_stat.st_mode)
                assert previous_temp is not None
                cls._write_temporary(previous_temp, previous_bytes, opener, previous_mode, preserve_mode=True)
                cls._replace_sibling(previous_temp, previous_path, parent_stat)
                previous_temp = None
                cls._sync_parent_directory(path, parent_stat)

            # Recheck the target to reject a link or type substitution immediately
            # before the atomic publication step.
            cls._regular_file_stat(path)
            cls._replace_sibling(new_temp, path, parent_stat)
            new_temp = None
            try:
                directory_synced = cls._sync_parent_directory(path, parent_stat)
            except OSError as error:
                raise cls.durability_error(path, error) from error
            if not directory_synced:
                logger.warning(f"Metadata '{path}' was atomically published, but parent-directory durability is unavailable.")
        finally:
            cls._cleanup_temporaries(new_temp, previous_temp)

    @classmethod
    def _read_previous_version(cls, path: Path, current_stat: os.stat_result, opener: Callable) -> bytes:
        """Read the prior version and reject a file changed during that read."""
        previous_bytes = cls.read_bytes(path, opener=opener)
        after_read_stat = cls._regular_file_stat(path)
        if (
            after_read_stat is None
            or not os.path.samestat(current_stat, after_read_stat)
            or (current_stat.st_size != after_read_stat.st_size or current_stat.st_mtime_ns != after_read_stat.st_mtime_ns)
        ):
            raise OSError(f"{cls.path_label} '{path}' changed while preparing its replacement.")
        return previous_bytes

    @classmethod
    def _cleanup_temporaries(cls, new_temp: Path | None, previous_temp: Path | None) -> None:
        """Remove only still-owned temporary entries without masking the main result."""
        for temporary_path in (new_temp, previous_temp):
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError as error:
                    logger.warning(f"Could not remove metadata staging file '{temporary_path}': {error}")
