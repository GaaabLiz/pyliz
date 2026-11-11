"""Staged snapshot installation, legacy merge and installed-copy removal."""

import shutil
import stat
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pylizlib.core.data.gen import gen_random_string
from pylizlib.core.log.pylizLogger import logger
from pylizlib.core.os.path import remove_directory_or_move_to_temp
from pylizlib.core.os.snap.callbacks import report_directory_progress
from pylizlib.core.os.snap.integrity import SnapshotIntegrityError
from pylizlib.core.os.snap.storage.context import SnapshotStorage
from pylizlib.core.os.snap.storage.publication import cleanup_after_commit
from pylizlib.core.os.snap.storage.tree import assert_no_symlinks
from pylizlib.core.os.utils import is_critical_system_path


@dataclass(frozen=True)
class InstallReplacement:
    """Prepared installation paths, recorded only after the copy succeeds.

    The backup may be absent when the destination did not exist. Its existence
    retains the legacy decision about whether rollback can restore that target.
    """

    install_loc: Path
    staging_dir: Path
    backup_dir: Path


class SnapshotInstaller:
    """Install or remove live copies without changing the stored snapshot data.

    Replacement and top-level merge intentionally have different recovery
    behavior. Last-used metadata is saved after the content transaction.
    """

    def __init__(self, storage: SnapshotStorage):
        """Use the live model and validated storage paths for this invocation."""
        self.storage = storage

    def install(self, enable_everyone_full_control: bool = False, clear_destination: bool = True, progress_callback=None, message_callback=None):
        """
        Installs the snapshot's contents to their original locations on the filesystem.
        This will clear the destination directories before copying the snapshot's contents.

        Args:
            enable_everyone_full_control (bool): If True and on Windows, it will attempt
                to set full control permissions for the 'Everyone' group on the
                installed directories. Defaults to False; ACL changes require explicit opt-in.
            clear_destination (bool): If True, clears the destination directories before copying.
        """
        self.storage.snapshot.validate()
        self.storage.root_path()
        import platform
        import sys

        if self.storage.snapshot.os_created and self.storage.snapshot.os_created != platform.system():
            raise RuntimeError(f"Cannot install snapshot: created on {self.storage.snapshot.os_created}, but current OS is {platform.system()}.")

        if enable_everyone_full_control and sys.platform == "win32":
            try:
                import ntsecuritycon as con
                import win32security
            except ImportError:
                logger.error("pywin32 not installed, cannot set file permissions.")
                win32security = None
        else:
            win32security = None

        total_dirs = len(self.storage.snapshot.directories)

        self._preflight()

        rollbacks = []
        try:
            self._stage_directories(rollbacks, total_dirs, progress_callback, message_callback)

            self._publish_directories(rollbacks, clear_destination)

            self._apply_windows_permissions(rollbacks, enable_everyone_full_control, win32security, con if win32security else None)

        except Exception as e:
            # 5. Ripristinare la vecchia directory se lo swap fallisce
            logger.error(f"Installation failed during transaction. Rolling back. Reason: {e}")
            self._rollback_installation(rollbacks, clear_destination)
            raise

        self._record_last_used()
        cleanup_after_commit((path for rb in rollbacks for path in (rb.backup_dir, rb.staging_dir)), "Installation")

    def remove_installed_copies(self, message_callback=None):
        """
        Removes all directories on the system that this snapshot is managing.
        This is effectively an 'uninstall' operation for the snapshot's associated directories.
        It only removes the copies at the 'original_path' locations, not the snapshot's
        internal backup.

        Raises:
            ExceptionGroup: If any target could not be removed. Other targets
                            are still attempted, and metadata is left unchanged.
        """
        failures = []
        for dir_assoc in self.storage.snapshot.directories:
            install_path = Path(dir_assoc.original_path)

            if is_critical_system_path(install_path):
                raise ValueError(f"Cannot remove installed copy at '{install_path}': it is a critical system path.")

            try:
                try:
                    mode = install_path.lstat().st_mode
                except FileNotFoundError:
                    logger.debug(f"Install path '{install_path}' does not exist. Skipping.")
                    continue
                if not (stat.S_ISDIR(mode) or stat.S_ISLNK(mode)):
                    raise NotADirectoryError(f"Install path '{install_path}' is not a directory.")
                logger.info(f"Removing installed copy at '{install_path}'")
                remove_directory_or_move_to_temp(install_path, message_callback=message_callback)
            except Exception as e:
                logger.error(f"Failed to remove directory '{install_path}': {e}")
                e.add_note(f"Installed copy: {install_path}")
                failures.append(e)
        if failures:
            raise ExceptionGroup("Failed to remove one or more installed copies.", failures)

    def _preflight(self) -> None:
        """Validate stored sources, targets and legacy-manifest policy before copying."""
        # 1. Preflight
        for dir_assoc in self.storage.snapshot.directories:
            source_dir = self.storage.child_path(dir_assoc.directory_name)
            if not source_dir.exists() or not source_dir.is_dir():
                raise FileNotFoundError(f"Source directory '{source_dir}' does not exist inside the snapshot.")
            assert_no_symlinks(source_dir)
            install_location = Path(dir_assoc.original_path)
            if is_critical_system_path(install_location):
                raise ValueError(f"Cannot install to '{install_location}': it is a critical system path.")
            if dir_assoc.integrity_manifest is None:
                if not self.storage.settings.allow_unverified_legacy_snapshots:
                    raise SnapshotIntegrityError(f"Snapshot association '{dir_assoc.folder_id}' has no integrity manifest; refusing unverified installation.")
                logger.warning(
                    "Snapshot association '%s' has no integrity manifest; content verification is unavailable.",
                    dir_assoc.folder_id,
                )

    def _stage_directories(self, rollbacks: list[InstallReplacement], total_dirs: int, progress_callback, message_callback) -> None:
        """Prepare and verify every copy before replacing any live destination."""
        for i, dir_assoc in enumerate(self.storage.snapshot.directories):
            source_dir = self.storage.child_path(dir_assoc.directory_name)
            install_location = Path(dir_assoc.original_path)

            # 2. Copiare in una directory temporanea (Staging)
            staging_dir = install_location.with_name(f"{install_location.name}_staging_{gen_random_string(6)}")
            backup_dir = install_location.with_name(f"{install_location.name}_bck_{gen_random_string(6)}")

            def copy_progress(copied_bytes: int, total_bytes: int) -> None:
                """Adapt verified-copy byte counts to snapshot percentage notifications."""
                report_directory_progress(progress_callback, i, total_dirs, copied_bytes, total_bytes)

            logger.info(f"Copying '{source_dir}' to staging '{staging_dir}'")
            try:
                assert_no_symlinks(source_dir)
                self.storage.settings.copy_strategy.copy_directory(
                    source_dir,
                    staging_dir,
                    progress_callback=copy_progress if progress_callback else None,
                    message_callback=message_callback,
                    expected_manifest=dir_assoc.integrity_manifest,
                )
                assert_no_symlinks(staging_dir)
            except SnapshotIntegrityError:
                if staging_dir.exists():
                    shutil.rmtree(staging_dir)
                raise
            except Exception as e:
                if staging_dir.exists():
                    shutil.rmtree(staging_dir)
                raise RuntimeError(f"Failed to copy to staging '{staging_dir}': {e}") from e

            # 3. La strategia ha verificato il manifest prima di pubblicare lo staging.

            rollbacks.append(InstallReplacement(install_location, staging_dir, backup_dir))

    def _publish_directories(self, rollbacks: list[InstallReplacement], clear_destination: bool) -> None:
        """Publish prepared copies using replacement or the legacy top-level merge."""
        # 4. Sostituire la destinazione soltanto dopo il completamento di tutti gli staging
        for rb in rollbacks:
            install_loc = rb.install_loc
            staging_dir = rb.staging_dir
            backup_dir = rb.backup_dir

            install_loc.parent.mkdir(parents=True, exist_ok=True)

            if clear_destination:
                if install_loc.exists():
                    install_loc.rename(backup_dir)
                staging_dir.rename(install_loc)
            else:
                if not install_loc.exists():
                    install_loc.mkdir(parents=True, exist_ok=True)
                # Spostamento manuale per merge
                for item in staging_dir.iterdir():
                    dst = install_loc / item.name
                    if dst.exists():
                        if dst.is_dir():
                            shutil.rmtree(dst)
                        else:
                            dst.unlink()
                    shutil.move(str(item), str(dst))

    def _apply_windows_permissions(self, rollbacks: list[InstallReplacement], enabled: bool, win32security, con) -> None:
        """Apply opted-in Windows ACLs, logging individual failures without aborting."""
        if enabled and win32security:
            for rb in rollbacks:
                install_loc = rb.install_loc
                try:
                    everyone, domain, type = win32security.LookupAccountName("", "Everyone")
                    sd = win32security.GetFileSecurity(str(install_loc), win32security.DACL_SECURITY_INFORMATION)
                    dacl = sd.GetSecurityDescriptorDacl()
                    dacl.AddAccessAllowedAceEx(
                        win32security.ACL_REVISION,
                        con.OBJECT_INHERIT_ACE | con.CONTAINER_INHERIT_ACE,
                        con.GENERIC_ALL,
                        everyone,
                    )
                    sd.SetSecurityDescriptorDacl(1, dacl, 0)
                    win32security.SetFileSecurity(str(install_loc), win32security.DACL_SECURITY_INFORMATION, sd)
                except Exception as e:
                    logger.error(f"Failed to set permissions on '{install_loc}': {e}")

    def _rollback_installation(self, rollbacks: list[InstallReplacement], clear_destination: bool) -> None:
        """Remove staging and restore existing backups in the original iteration order."""
        for rb in rollbacks:
            install_loc = rb.install_loc
            staging_dir = rb.staging_dir
            backup_dir = rb.backup_dir

            if staging_dir.exists():
                shutil.rmtree(staging_dir)

            if clear_destination and backup_dir.exists():
                if install_loc.exists():
                    shutil.rmtree(install_loc)
                backup_dir.rename(install_loc)

    def _record_last_used(self) -> None:
        """Save usage metadata after publication; failures do not roll back contents."""
        # 7. Aggiornare `date_last_used` soltanto dopo commit riuscito
        self.storage.snapshot.date_last_used = datetime.now()
        self.storage.metadata.update_field(
            self.storage.child_path(self.storage.settings.json_filename),
            "date_last_used",
            self.storage.snapshot.date_last_used.isoformat(),
        )
