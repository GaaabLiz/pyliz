"""Staged snapshot installation, legacy merge and installed-copy removal."""

import os
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
from pylizlib.core.os.snap.operations.destinations import validate_destructive_destinations
from pylizlib.core.os.snap.storage.context import SnapshotStorage
from pylizlib.core.os.snap.storage.transactions import (
    SnapshotTransactionJournal,
    prepare_snapshot_metadata,
    recover_storage_transactions,
    rename_and_sync,
)
from pylizlib.core.os.snap.storage.tree import assert_no_symlinks
from pylizlib.core.os.windows.security import grant_everyone_full_control


class SnapshotInstallMetadataError(RuntimeError):
    """Report that installation committed but its last-used metadata update failed.

    ``metadata_published`` is True when the metadata adapter confirms that the
    new JSON was published, False when it confirms publication did not happen,
    and None when the adapter cannot report the publication state.

    Attributes:
        installation_completed (bool): Always True; installed content is not rolled back.
        metadata_field (str): Always date_last_used, the completion field being saved.
        metadata_published (bool | None): Confirmed publication, confirmed absence of
            publication, or unknown outcome. The journal may complete it on recovery.
        durability_confirmed (bool | None): Adapter's directory-flush outcome, if known.
    """

    def __init__(self, metadata_published: bool | None, durability_confirmed: bool | None):
        """Store metadata outcome after successful content installation.

        Args:
            metadata_published (bool | None): Publication state reported by the adapter.
            durability_confirmed (bool | None): Durability state reported by the adapter.

        Returns:
            None: The exception retains both flags and identifies the installed content.
        """
        super().__init__("Snapshot contents were installed, but completion of the date_last_used update could not be confirmed.")
        self.installation_completed = True
        self.metadata_field = "date_last_used"
        self.metadata_published = metadata_published
        self.durability_confirmed = durability_confirmed


@dataclass(frozen=True)
class InstallReplacement:
    """Planned installation paths, chosen before staging begins.

    The backup may be absent when the destination did not exist. Its existence
    retains the legacy decision about whether rollback can restore that target.

    Attributes:
        install_loc (Path): Absolute lexical target of the installed association.
        staging_dir (Path): Generated sibling receiving the verified stored content.
        backup_dir (Path): Generated sibling retaining any previous target.
        folder_id (str): Stable association identity used for metadata and recovery.
        had_original (bool): Whether lstat observed a target during planning; no path
            reservation is implied and publication checks for concurrent changes.
    """

    install_loc: Path
    staging_dir: Path
    backup_dir: Path
    folder_id: str
    had_original: bool


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

        Raises:
            SnapshotInstallMetadataError: If the directory installation committed but
                updating ``date_last_used`` failed. Temporary old copies are retained
                for recovery when replacement mode staged them, and
                ``metadata_published`` describes the JSON outcome when the metadata
                adapter can report it.
        """
        self.storage.snapshot.validate()
        self.storage.root_path()
        validate_destructive_destinations(
            [(association.folder_id, association.original_path) for association in self.storage.snapshot.directories],
            catalogue_path=self.storage.path_catalogue,
            origin_os=self.storage.snapshot.os_created,
            operation="install snapshot",
        )
        recover_storage_transactions(self.storage)

        win32security, con = self._permission_backend(enable_everyone_full_control)

        logger.info("Installing snapshot id=%s associations=%s clear_destination=%s", self.storage.snapshot.id, len(self.storage.snapshot.directories), clear_destination)
        total_dirs = len(self.storage.snapshot.directories)

        self._preflight()

        previous_date = self.storage.snapshot.date_last_used
        last_used = datetime.now()
        replacements = self._plan_replacements()
        staging_roots = [rb.staging_dir for rb in replacements]
        journal = self._begin_install_journal(replacements, staging_roots, clear_destination)
        try:
            metadata_info = prepare_snapshot_metadata(
                self.storage,
                journal.workspace,
                field_name="date_last_used",
                field_value=last_used.isoformat(),
            )
            journal.update_payload(metadata=metadata_info)
            self._stage_directories(replacements, total_dirs, progress_callback, message_callback)

            merge_entries = []
            if not clear_destination:
                merge_entries = self._plan_merge_entries(replacements)
                journal.update_payload(entries=merge_entries)
            self._publish_directories(replacements, clear_destination, merge_entries)

            self._apply_windows_permissions(replacements, enable_everyone_full_control, win32security, con)
            journal.set_state("commit_decided")
        except Exception as error:
            logger.error(f"Installation failed during transaction. Rolling back. Reason: {error}")
            try:
                journal.decide_rollback(self.storage)
            except Exception as rollback_error:
                logger.error(f"Installation rollback is incomplete; journal retained at '{journal.path}': {rollback_error}")
                error.add_note(f"Persistent recovery journal retained at '{journal.path}'.")
            raise

        self._complete_install_metadata(journal, metadata_info, last_used, previous_date)
        cleanup_paths = [rb.backup_dir for rb in replacements]
        cleanup_paths.extend(staging_roots)
        journal.finalize(cleanup_paths, "Installation")
        logger.info("Installed snapshot id=%s", self.storage.snapshot.id)

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
        validate_destructive_destinations(
            [(association.folder_id, association.original_path) for association in self.storage.snapshot.directories],
            catalogue_path=self.storage.path_catalogue,
            origin_os=self.storage.snapshot.os_created if self.storage.snapshot.directories else None,
            operation="remove installed copies",
        )
        failures = []
        for dir_assoc in self.storage.snapshot.directories:
            install_path = Path(dir_assoc.original_path)

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
        """Validate stored sources and manifests before copying."""
        # Preflight
        for dir_assoc in self.storage.snapshot.directories:
            source_dir = self.storage.child_path(dir_assoc.directory_name)
            if not source_dir.exists() or not source_dir.is_dir():
                raise FileNotFoundError(f"Source directory '{source_dir}' does not exist inside the snapshot.")
            assert_no_symlinks(source_dir)
            if dir_assoc.integrity_manifest is None:
                if not self.storage.settings.allow_unverified_legacy_snapshots:
                    raise SnapshotIntegrityError(f"Snapshot association '{dir_assoc.folder_id}' has no integrity manifest; refusing unverified installation.")
                logger.warning(
                    "Snapshot association '%s' has no integrity manifest; content verification is unavailable.",
                    dir_assoc.folder_id,
                )

    def _plan_replacements(self) -> list[InstallReplacement]:
        """Choose unique stage and backup names before publishing the journal."""
        replacements = []
        for association in self.storage.snapshot.directories:
            install_location = Path(os.path.abspath(association.original_path))
            staging_dir = install_location.with_name(f"{install_location.name}_staging_{gen_random_string(6)}")
            backup_dir = install_location.with_name(f"{install_location.name}_bck_{gen_random_string(6)}")
            if staging_dir.exists() or staging_dir.is_symlink() or backup_dir.exists() or backup_dir.is_symlink():
                raise FileExistsError(f"Could not reserve installation staging names beside '{install_location}'.")
            try:
                install_location.lstat()
                had_original = True
            except FileNotFoundError:
                had_original = False
            replacements.append(InstallReplacement(install_location, staging_dir, backup_dir, association.folder_id, had_original))
        return replacements

    def _stage_directories(self, replacements: list[InstallReplacement], total_dirs: int, progress_callback, message_callback) -> None:
        """Prepare and verify every copy before replacing any live destination."""
        associations = {association.folder_id: association for association in self.storage.snapshot.directories}
        for i, replacement in enumerate(replacements):
            dir_assoc = associations[replacement.folder_id]
            source_dir = self.storage.child_path(dir_assoc.directory_name)
            staging_dir = replacement.staging_dir

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

            # La strategia ha verificato il manifest prima di pubblicare lo staging.

    def _plan_merge_entries(self, replacements: list[InstallReplacement]) -> list[dict]:
        """Record every top-level merge replacement before modifying live copies."""
        entries = []
        for replacement in replacements:
            for staged_item in sorted(replacement.staging_dir.iterdir()):
                destination = replacement.install_loc / staged_item.name
                backup = destination.with_name(f"{destination.name}_bck_{gen_random_string(6)}")
                if backup.exists() or backup.is_symlink():
                    raise FileExistsError(f"Could not reserve merge backup '{backup}'.")
                try:
                    destination.lstat()
                    had_original = True
                except FileNotFoundError:
                    had_original = False
                entries.append(
                    {
                        "folder_id": replacement.folder_id,
                        "stage": staged_item.as_posix(),
                        "stage_root": replacement.staging_dir.as_posix(),
                        "destination": destination.as_posix(),
                        "backup": backup.as_posix(),
                        "had_original": had_original,
                        "merge_child": True,
                    }
                )
        return entries

    def _publish_directories(self, replacements: list[InstallReplacement], clear_destination: bool, merge_entries: list[dict]) -> None:
        """Publish prepared copies using replacement or the legacy top-level merge."""
        # Sostituire la destinazione soltanto dopo il completamento di tutti gli staging
        for rb in replacements:
            install_loc = rb.install_loc
            staging_dir = rb.staging_dir
            backup_dir = rb.backup_dir

            install_loc.parent.mkdir(parents=True, exist_ok=True)

            if clear_destination:
                if rb.had_original:
                    if not (install_loc.exists() or install_loc.is_symlink()):
                        raise FileNotFoundError(f"Install destination '{install_loc}' disappeared before publication.")
                    rename_and_sync(install_loc, backup_dir)
                elif install_loc.exists() or install_loc.is_symlink():
                    raise FileExistsError(f"Install destination '{install_loc}' appeared during staging.")
                rename_and_sync(staging_dir, install_loc)
            else:
                if not install_loc.exists():
                    install_loc.mkdir(parents=True, exist_ok=True)
        if not clear_destination:
            for entry in merge_entries:
                staged_item = Path(entry["stage"])
                destination = Path(entry["destination"])
                backup = Path(entry["backup"])
                if entry["had_original"]:
                    if not (destination.exists() or destination.is_symlink()):
                        raise FileNotFoundError(f"Merge destination '{destination}' disappeared before publication.")
                    rename_and_sync(destination, backup)
                elif destination.exists() or destination.is_symlink():
                    raise FileExistsError(f"Merge destination '{destination}' appeared during staging.")
                rename_and_sync(staged_item, destination)

    def _apply_windows_permissions(self, replacements: list[InstallReplacement], enabled: bool, win32security, con) -> None:
        """Apply opted-in Windows ACLs, logging individual failures without aborting."""
        if enabled and win32security:
            for rb in replacements:
                install_loc = rb.install_loc
                try:
                    grant_everyone_full_control(install_loc, security_api=win32security, con=con)
                except Exception as e:
                    logger.error(f"Failed to set permissions on '{install_loc}': {e}")

    def _begin_install_journal(self, replacements: list[InstallReplacement], staging_roots: list[Path], clear_destination: bool) -> SnapshotTransactionJournal:
        """Persist every owned replacement path before creating a staging copy.

        Args:
            replacements (list[InstallReplacement]): Complete ordered installation plan.
            staging_roots (list[Path]): Generated sibling roots owned by this operation.
            clear_destination (bool): Whether entries replace entire roots; merge
                entries are filled in only after staging reveals their top-level members.

        Returns:
            SnapshotTransactionJournal: Prepared v1 installation journal.

        Raises:
            OSError: If the intent cannot be persisted before changes begin.
        """
        journal_payload = {
            "entries": [],
            "staging_roots": [path.as_posix() for path in staging_roots],
            "clear_destination": clear_destination,
        }
        if clear_destination:
            journal_payload["entries"] = [
                {
                    "folder_id": rb.folder_id,
                    "stage": rb.staging_dir.as_posix(),
                    "stage_root": rb.staging_dir.as_posix(),
                    "destination": rb.install_loc.as_posix(),
                    "backup": rb.backup_dir.as_posix(),
                    "had_original": rb.had_original,
                }
                for rb in replacements
            ]
        return SnapshotTransactionJournal.begin(self.storage.path_snapshot, "install", journal_payload)

    def _complete_install_metadata(self, journal: SnapshotTransactionJournal, metadata_info: dict, last_used: datetime, previous_date: datetime | None) -> None:
        """Publish last-used metadata after the contents have crossed their commit boundary.

        Args:
            journal (SnapshotTransactionJournal): Commit-decided installation journal.
            metadata_info (dict): Workspace-relative staged metadata filenames.
            last_used (datetime): Proposed local date_last_used for this installation.
            previous_date (datetime | None): Prior live value retained if publication fails.

        Returns:
            None: After metadata publication, live-model update and committed state.

        Raises:
            SnapshotInstallMetadataError: Contents are installed, while metadata or
                final journal persistence failed. Publication flags describe the outcome.
        """
        try:
            new_metadata = self.storage.metadata.read_bytes(journal.workspace / metadata_info["new"])
            self.storage.metadata.write_bytes(self.storage.path_snapshot_json, new_metadata)
        except Exception as error:
            metadata_published = getattr(error, "published", None)
            durability_confirmed = getattr(error, "durability_confirmed", None)
            metadata_published = metadata_published if type(metadata_published) is bool else None
            durability_confirmed = durability_confirmed if type(durability_confirmed) is bool else None
            self.storage.snapshot.date_last_used = last_used if metadata_published is True else previous_date
            raise SnapshotInstallMetadataError(metadata_published, durability_confirmed) from error

        self.storage.snapshot.date_last_used = last_used
        try:
            journal.set_state("committed")
        except Exception as error:
            raise SnapshotInstallMetadataError(True, getattr(error, "durability_confirmed", None)) from error

    @staticmethod
    def _permission_backend(enable_everyone_full_control: bool):
        """Load optional Windows permission APIs only after explicit user opt-in."""
        import sys

        if enable_everyone_full_control and sys.platform == "win32":
            try:
                import ntsecuritycon as con
                import win32security
            except ImportError:
                logger.error("pywin32 not installed, cannot set file permissions.")
                win32security = None
        else:
            win32security = None
        return win32security, con if win32security else None
