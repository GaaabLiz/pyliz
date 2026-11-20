"""Staged snapshot installation, legacy merge and installed-copy removal."""

import hashlib
import shutil
import stat
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pylizlib.core.data.gen import gen_random_string
from pylizlib.core.log.pylizLogger import logger
from pylizlib.core.os.filesystem.directories import remove_directory_or_move_to_temp
from pylizlib.core.os.filesystem.tree import is_link_or_junction
from pylizlib.core.os.snap.callbacks import report_directory_progress
from pylizlib.core.os.snap.domain import SnapDirAssociation
from pylizlib.core.os.snap.integrity import SnapshotIntegrityError
from pylizlib.core.os.snap.operations.archives import SnapshotArchiveService
from pylizlib.core.os.snap.operations.destinations import validate_destructive_destinations
from pylizlib.core.os.snap.storage.context import SnapshotStorage
from pylizlib.core.os.snap.storage.coordination import coordinated
from pylizlib.core.os.snap.storage.install_registry import InstalledCopy, InstalledCopyRegistry
from pylizlib.core.os.snap.storage.transactions import (
    SnapshotTransactionJournal,
    prepare_snapshot_metadata,
    recover_storage_transactions,
    rename_and_sync,
)
from pylizlib.core.os.snap.storage.tree import assert_no_symlinks
from pylizlib.core.os.windows.security import grant_everyone_full_control


class SnapshotInstallMetadataError(RuntimeError):
    """Report that installation committed but completion metadata could not be confirmed.

    ``metadata_published`` is True when the adapter confirms that the field
    named by ``metadata_field`` was published, False when it confirms
    publication did not happen, and None when the adapter cannot report the
    publication state.

    Attributes:
        installation_completed (bool): Always True; installed content is not rolled back.
        metadata_field (str): Metadata item whose publication could not be confirmed.
        metadata_published (bool | None): Confirmed publication, confirmed absence of publication, or unknown
            outcome. The journal may complete it on recovery.
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
        super().__init__("Snapshot contents were installed, but completion metadata could not be confirmed.")
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
        folder_id (str): Non-empty stable association identity; physical storage uses its digest, so it need not
            be a path component.
        had_original (bool): Whether lstat observed a target during planning; no path reservation is implied and
            publication checks for concurrent changes.
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

    Attributes:
        storage (SnapshotStorage): Live snapshot model, settings, captured layout and protected metadata adapter
            for this operation.
    """

    def __init__(self, storage: SnapshotStorage):
        """Use the live model and validated storage paths for this invocation.

        Args:
            storage (SnapshotStorage): Live snapshot model, settings, captured layout and protected metadata adapter
                for this operation.

        Returns:
            None: No return value.
        """
        self.storage = storage

    @coordinated("storage.path_catalogue")
    def install(self, enable_everyone_full_control: bool = False, clear_destination: bool = True, progress_callback=None, message_callback=None):
        """Installs the snapshot's contents to their original locations on the filesystem.
        Copies are prepared and verified in staging before live destinations are replaced or merged.

        Args:
            enable_everyone_full_control (bool): If True and on Windows, it will attempt to set full control
                permissions for the 'Everyone' group on the installed directories. Defaults to False; ACL changes
                require explicit opt-in.
            clear_destination (bool): Replace entire live roots after all staging copies complete when True; False
                merges by replacing colliding top-level children and retaining unrelated ones.
            progress_callback (SnapshotPercentCallback | None): Optional observer receiving integer aggregate
                percentage from 0 through 100; return values do not cancel the operation.
            message_callback (MessageCallback | None): Optional status observer receiving one message string; its
                exceptions propagate according to the calling operation.

        Returns:
            None: No return value.

        Raises:
            SnapshotBusyError: Another operation owns the catalogue, or an observer attempts a modifying call.
            SnapshotInstallMetadataError: If the directory installation committed but updating ``date_last_used``
                or the installed-destination registry failed. Temporary old copies are retained for recovery when
                replacement mode staged them, and ``metadata_field`` identifies the failed update.

        Notes:
            All copies are staged before any live replacement. Whole-root replacement and top-level merge retain
            distinct journal plans. Metadata and destination registration follow the content commit;
            SnapshotInstallMetadataError means contents remain installed and the journal may complete the updates on
            recovery.
        """
        self.storage.snapshot.validate()
        self.storage.root_path()
        validate_destructive_destinations(
            [(association.folder_id, association.original_path) for association in self.storage.snapshot.directories],
            catalogue_path=self.storage.path_catalogue,
            origin_os=self.storage.snapshot.os_created,
            operation="install snapshot",
        )
        self._validate_existing_targets()
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

    @coordinated("storage.path_catalogue")
    def get_removable_paths(self) -> list[Path] | None:
        """Return registered, present real directories; None means legacy state is unknown.

        Returns:
            list[Path] | None: Present registered directories, an empty list when none are present, or None when
                installation history is unknown.

        Raises:
            RuntimeError: A previous removal is pending review.
            ValueError: A registered target is unsafe for removal.
        """
        recover_storage_transactions(self.storage)
        records = InstalledCopyRegistry(self.storage.path_catalogue).get(self.storage.snapshot.id)
        if records is None:
            return None
        if any(record.state == "removing" for record in records):
            raise RuntimeError("A previous removal was interrupted; review the local backup before retrying.")
        targets = self._existing_registered_targets(records, reject_invalid=True)
        if targets:
            validate_destructive_destinations(
                [(record.folder_id, path) for record, path in targets],
                catalogue_path=self.storage.path_catalogue,
                origin_os=self.storage.snapshot.os_created,
                operation="remove installed copies",
            )
        return [path for _, path in targets]

    @coordinated("storage.path_catalogue")
    def remove_installed_copies(self, message_callback=None) -> Path | None:
        """Back up and remove only destinations recorded by a completed installation.

        Args:
            message_callback (MessageCallback | None): Optional status observer receiving one message string; its
                exceptions propagate according to the calling operation.

        Returns:
            Path | None: Published backup path, or None when there are no registered local copies to remove.

        Raises:
            RuntimeError: Legacy installation history is unknown or a previous removal needs review.
            ExceptionGroup: One or more directories or registration updates failed; successful removals remain
                unregistered while failed targets remain recorded.
            NotADirectoryError: A registered destination is no longer a real directory.
            SnapshotIncompleteError: A selected directory cannot be completely backed up; nothing is removed.
            ValueError: Backup storage is not configured or a registered target is unsafe.
        """
        recover_storage_transactions(self.storage)
        registry = InstalledCopyRegistry(self.storage.path_catalogue)
        records = registry.get(self.storage.snapshot.id)
        if records is None:
            raise RuntimeError(
                "Installed destinations are unknown for this legacy snapshot. Install it once with this version before automatic removal."
            )
        if any(record.state == "removing" for record in records):
            raise RuntimeError("A previous removal was interrupted; review the local backup before retrying.")

        targets = self._existing_registered_targets(records, reject_invalid=True)
        if not targets:
            registry.set(self.storage.snapshot.id, [])
            return None

        validate_destructive_destinations(
            [(record.folder_id, path) for record, path in targets],
            catalogue_path=self.storage.path_catalogue,
            origin_os=self.storage.snapshot.os_created,
            operation="remove installed copies",
        )
        backup_path = self.storage.settings.backup_path
        if backup_path is None:
            raise ValueError("Cannot remove installed copies without a configured backup_path.")

        backup_associations = self._backup_associations(targets)
        backup = SnapshotArchiveService(self.storage).create_backup_for_associations(backup_path, "beforeRemove", backup_associations, message_callback)

        # Prune destinations that were already absent only after the full backup succeeds.
        remaining = [record for record, _ in targets]
        registry.set(self.storage.snapshot.id, remaining)
        failures = []
        for record, path in targets:
            pending = [
                InstalledCopy(current.folder_id, current.path, "removing")
                if (current.folder_id, current.path) == (record.folder_id, record.path)
                else current
                for current in remaining
            ]
            try:
                registry.set(self.storage.snapshot.id, pending)
            except Exception as error:
                error.add_note(f"Could not mark '{path}' as pending removal; no directory was removed.")
                failures.append(error)
                break
            remaining = pending

            try:
                logger.info("Removing registered installed copy at '%s'", path)
                remove_directory_or_move_to_temp(path, message_callback=message_callback)
            except Exception as error:
                try:
                    path.lstat()
                    path_was_removed = False
                except FileNotFoundError:
                    path_was_removed = True
                except OSError as inspect_error:
                    error.add_note(f"Could not inspect '{path}' after the removal error; its record remains pending: {inspect_error}")
                    failures.append(error)
                    break

                if path_was_removed:
                    remaining = [current for current in remaining if (current.folder_id, current.path) != (record.folder_id, record.path)]
                    try:
                        registry.set(self.storage.snapshot.id, remaining)
                    except Exception as registry_error:
                        error.add_note(f"The directory is absent, but its installation record could not be updated: {registry_error}")
                        failures.append(error)
                        break
                    error.add_note(f"The directory is absent and was unregistered: {path}")
                    failures.append(error)
                    continue

                restored = [
                    InstalledCopy(current.folder_id, current.path, "installed")
                    if (current.folder_id, current.path) == (record.folder_id, record.path)
                    else current
                    for current in remaining
                ]
                try:
                    registry.set(self.storage.snapshot.id, restored)
                    remaining = restored
                except Exception as restore_error:
                    error.add_note(f"Removal state remains pending for '{path}': {restore_error}")
                    failures.append(error)
                    break
                logger.error("Failed to remove installed directory '%s': %s", path, error)
                error.add_note(f"Installed copy: {path}")
                failures.append(error)
                continue

            remaining = [current for current in remaining if (current.folder_id, current.path) != (record.folder_id, record.path)]
            try:
                registry.set(self.storage.snapshot.id, remaining)
            except Exception as error:
                error.add_note(f"The directory was removed, but its installation record could not be updated: {path}")
                failures.append(error)
                break

        if failures:
            raise ExceptionGroup("Failed to remove one or more installed copies.", failures)
        return backup

    def _existing_registered_targets(self, records: list[InstalledCopy], *, reject_invalid: bool) -> list[tuple[InstalledCopy, Path]]:
        """Select currently present real directories from a persisted install record.

        Args:
            records (list[InstalledCopy]): Persisted destinations to inspect.
            reject_invalid (bool): Raise when a present destination is not a real directory instead of skipping it.

        Returns:
            list[tuple[InstalledCopy, Path]]: Records paired with their present, non-link directory paths.

        Raises:
            NotADirectoryError: A present registered destination is not a real directory and reject_invalid is true.
        """
        targets = []
        for record in records:
            if record.state != "installed":
                continue
            path = record.path
            try:
                mode = path.lstat().st_mode
            except FileNotFoundError:
                continue
            if is_link_or_junction(path) or not stat.S_ISDIR(mode):
                if reject_invalid:
                    raise NotADirectoryError(f"Registered install destination '{path}' is not a real directory.")
                continue
            targets.append((record, path))
        return targets

    @staticmethod
    def _backup_associations(targets: list[tuple[InstalledCopy, Path]]) -> list[SnapDirAssociation]:
        """Build an archive-only association list for the recorded local destinations.

        Args:
            targets (list[tuple[InstalledCopy, Path]]): Registered records paired with destinations selected for backup.

        Returns:
            list[SnapDirAssociation]: Archive associations using unique IDs and the selected absolute paths.
        """
        associations = []
        used_ids = set()
        for index, (record, path) in enumerate(targets):
            folder_id = record.folder_id
            if folder_id in used_ids:
                folder_id = f"{folder_id}_{hashlib.sha256(path.as_posix().encode('utf-8')).hexdigest()[:12]}"
            while folder_id in used_ids:
                folder_id += "_copy"
            used_ids.add(folder_id)
            associations.append(SnapDirAssociation(index=index, original_path=path.as_posix(), folder_id=folder_id))
        return associations

    def _preflight(self) -> None:
        """Validate stored sources and manifests before copying.

        Returns:
            None: No return value.

        Raises:
            FileNotFoundError: A required source, stored association or metadata entry is absent.
            SnapshotIntegrityError: Captured and expected content differ in paths, entry types, sizes or SHA-256
                values.
        """

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
        """Choose unique stage and backup names before publishing the journal.

        Returns:
            list[InstallReplacement]: Ordered generated staging/backup/target plan; names are checked but not reserved
                against concurrent writers.

        Raises:
            FileExistsError: A destination or generated staging name already exists or changes before publication.
        """
        replacements = []
        for association in self.storage.snapshot.directories:
            install_location = Path(association.original_path).absolute()
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
        """Prepare and verify every copy before replacing any live destination.

        Args:
            replacements (list[InstallReplacement]): Complete ordered replacement plan, including target, staging and
                backup paths.
            total_dirs (int): Total associations receiving equal weight in aggregate progress.
            progress_callback (SnapshotPercentCallback | None): Optional observer receiving integer aggregate
                percentage from 0 through 100; return values do not cancel the operation.
            message_callback (MessageCallback | None): Optional status observer receiving one message string; its
                exceptions propagate according to the calling operation.

        Returns:
            None: No return value.

        Raises:
            RuntimeError: The requested operation cannot complete; a wrapped failure retains its original cause where
                documented.
        """
        associations = {association.folder_id: association for association in self.storage.snapshot.directories}
        for i, replacement in enumerate(replacements):
            dir_assoc = associations[replacement.folder_id]
            source_dir = self.storage.child_path(dir_assoc.directory_name)
            staging_dir = replacement.staging_dir

            def copy_progress(copied_bytes: int, total_bytes: int) -> None:
                """Adapt verified-copy byte counts to snapshot percentage notifications.

                Args:
                    copied_bytes (int): Bytes copied so far for the current directory, before clamping aggregate progress.
                    total_bytes (int): Estimated total bytes for progress; completed notifications use actual copied bytes,
                        including zero-byte trees.

                Returns:
                    None: No return value.
                """
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
        """Record every top-level merge replacement before modifying live copies.

        Args:
            replacements (list[InstallReplacement]): Complete ordered replacement plan, including target, staging and
                backup paths.

        Returns:
            list[dict]: Ordered top-level member replacements preserving unrelated live children; each record belongs
                to the install journal.

        Raises:
            FileExistsError: A destination or generated staging name already exists or changes before publication.
        """
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
        """Publish prepared copies using replacement or the legacy top-level merge.

        Args:
            replacements (list[InstallReplacement]): Complete ordered replacement plan, including target, staging and
                backup paths.
            clear_destination (bool): Replace entire live roots after all staging copies complete when True; False
                merges by replacing colliding top-level children and retaining unrelated ones.
            merge_entries (list[dict]): Top-level install replacements, persisted after staging and before changing
                live children.

        Returns:
            None: No return value.

        Raises:
            FileNotFoundError: A required source, stored association or metadata entry is absent.
            FileExistsError: A destination or generated staging name already exists or changes before publication.
        """

        # Revalidate the actual planned paths after copying, before the first live replacement.
        validate_destructive_destinations(
            [(replacement.folder_id, replacement.install_loc) for replacement in replacements],
            catalogue_path=self.storage.path_catalogue,
            origin_os=self.storage.snapshot.os_created,
            operation="publish installed copies",
        )

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
        """Apply opted-in Windows ACLs, logging individual failures without aborting.

        Args:
            replacements (list[InstallReplacement]): Complete ordered replacement plan, including target, staging and
                backup paths.
            enabled (bool): Whether the caller explicitly opted into the optional permission policy.
            win32security (ModuleType | None): Loaded pywin32 security API or None when disabled/unavailable.
            con (ModuleType | None): Loaded NT security constants or a compatible adapter supplying access/inheritance
                flags.

        Returns:
            None: No return value.
        """
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
            clear_destination (bool): Replace entire live roots after all staging copies complete when True; False
                merges by replacing colliding top-level children and retaining unrelated ones.

        Returns:
            SnapshotTransactionJournal: Prepared v1 installation journal.

        Raises:
            OSError: If the intent cannot be persisted before changes begin.
        """
        journal_payload = {
            "entries": [],
            "staging_roots": [path.as_posix() for path in staging_roots],
            "clear_destination": clear_destination,
            "installed_destinations": [
                {"folder_id": replacement.folder_id, "path": replacement.install_loc.as_posix()} for replacement in replacements
            ],
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
            SnapshotInstallMetadataError: Contents are installed, while metadata or final journal persistence failed.
                Publication flags describe the outcome.
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
            registry_records = [
                InstalledCopy(record["folder_id"], Path(record["path"]))
                for record in journal.payload["payload"].get("installed_destinations", [])
            ]
            InstalledCopyRegistry(self.storage.path_catalogue).register(self.storage.snapshot.id, registry_records)
        except Exception as error:
            metadata_published = getattr(error, "published", None)
            metadata_published = metadata_published if type(metadata_published) is bool else None
            durability_confirmed = getattr(error, "durability_confirmed", None)
            durability_confirmed = durability_confirmed if type(durability_confirmed) is bool else None
            metadata_error = SnapshotInstallMetadataError(metadata_published, durability_confirmed)
            metadata_error.metadata_field = "installed_destinations"
            raise metadata_error from error
        try:
            journal.set_state("committed")
        except Exception as error:
            raise SnapshotInstallMetadataError(True, getattr(error, "durability_confirmed", None)) from error

    def _validate_existing_targets(self) -> None:
        """Reject existing non-directory targets before installation can replace their entries.

        Returns:
            None: No return value.

        Raises:
            NotADirectoryError: An existing install destination is not a real directory.
        """
        for association in self.storage.snapshot.directories:
            path = Path(association.original_path)
            try:
                mode = path.lstat().st_mode
            except FileNotFoundError:
                continue
            if not stat.S_ISDIR(mode):
                raise NotADirectoryError(f"Install destination '{path}' exists but is not a real directory.")

    @staticmethod
    def _permission_backend(enable_everyone_full_control: bool):
        """Load optional Windows permission APIs only after explicit user opt-in.

        Args:
            enable_everyone_full_control (bool): Explicit opt-in for best-effort inheritable Everyone full-control
                ACLs on Windows; ignored elsewhere.

        Returns:
            tuple[ModuleType | None, ModuleType | None]: Security API and NT constants on opted-in Windows, otherwise
                (None, None); import failure is logged.
        """
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
