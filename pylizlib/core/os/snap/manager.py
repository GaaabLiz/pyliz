"""
Lifecycle manager for a single Snapshot instance.

Responsibilities (Single Responsibility Principle):
    - Creating, deleting, and duplicating a snapshot on the filesystem.
    - Installing a snapshot's contents to their original target locations.
    - Adding and removing individual directory associations.
    - Applying diff-based edit actions to a snapshot's contents.
    - Synchronising the snapshot's internal copy from live system directories.
    - Creating backup archives of a snapshot's data.

Classes:
    SnapshotManager – Manages all filesystem operations for one Snapshot.
"""

import os
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from pylizlib.core.data.gen import gen_random_string
from pylizlib.core.log.pylizLogger import logger
from pylizlib.core.os.path import duplicate_directory, remove_directory_or_move_to_temp
from pylizlib.core.os.snap.domain import (
    BackupType,
    SnapDirAssociation,
    SnapEditAction,
    SnapEditType,
    Snapshot,
    SnapshotSettings,
)
from pylizlib.core.os.snap.serializer import SnapshotSerializer
from pylizlib.core.os.snap.utils import SnapshotUtils
from pylizlib.core.os.utils import get_folder_size_mb, is_critical_system_path


class SnapshotManager:
    def __init__(
        self,
        snapshot: Snapshot,
        catalogue_path: Path,
        settings: SnapshotSettings = SnapshotSettings(),
    ):
        """
        Initializes a manager for a single snapshot's lifecycle.

        Args:
            snapshot: The `Snapshot` object to manage.
            catalogue_path: The root path of the snapshot catalogue.
            settings: Configuration settings for the manager.
        """
        self.snapshot = snapshot
        self.settings = settings
        self.path_catalogue = catalogue_path
        self.path_snapshot = SnapshotUtils.get_snapshot_path(self.snapshot.folder_name, self.path_catalogue)
        self.path_snapshot_json = SnapshotUtils.get_snapshot_json_path(self.snapshot.folder_name, self.path_catalogue, self.settings.json_filename)

    def __save_json(self):
        """Saves the current snapshot object state to its JSON file."""
        SnapshotSerializer.to_json(self.snapshot, self.path_snapshot_json)

    def create(self, progress_callback=None, message_callback=None, *, replace_existing: bool = False):
        """
        Creates the snapshot by preparing its contents and metadata in staging.

        Existing IDs are rejected unless replace_existing=True. An explicit
        replacement retains the old directory until publication succeeds and
        restores it if publication fails. Cleanup runs after commit.

        Raises:
            FileExistsError: If the destination exists and replacement is disabled.
        """
        if not replace_existing and (self.path_snapshot.exists() or self.path_snapshot.is_symlink()):
            raise FileExistsError(f"Snapshot destination '{self.path_snapshot}' already exists.")

        self.path_catalogue.mkdir(parents=True, exist_ok=True)
        transaction_path = Path(tempfile.mkdtemp(prefix=f"_staging_create_{self.snapshot.id}_", dir=self.path_catalogue))
        staging_path = transaction_path / "new"
        backup_path = transaction_path / "original"
        original_moved = False
        try:
            staging_path.mkdir()

            # We need to distribute the progress among directories if there are multiple.
            total_dirs = len(self.snapshot.directories)
            for i, snap_dir in enumerate(self.snapshot.directories):

                def dir_progress(copied, total):
                    if progress_callback:
                        # Calculate overall percentage based on dir index and dir progress
                        dir_pct = (copied / total) if total > 0 else 1.0
                        overall_pct = ((i + dir_pct) / total_dirs) * 100
                        progress_callback(int(overall_pct))

                snap_dir.copy_install_to(staging_path, progress_callback=dir_progress, message_callback=message_callback)

            # Write json to staging BEFORE making it the final destination
            SnapshotSerializer.to_json(self.snapshot, staging_path / self.settings.json_filename)

            if self.path_snapshot.exists() or self.path_snapshot.is_symlink():
                if not replace_existing:
                    raise FileExistsError(f"Snapshot destination '{self.path_snapshot}' already exists.")
                self.path_snapshot.rename(backup_path)
                original_moved = True
            staging_path.rename(self.path_snapshot)
        except Exception:
            if original_moved:
                # If rollback itself fails, preserve both copies in the
                # transaction directory instead of deleting recoverable data.
                backup_path.rename(self.path_snapshot)
            shutil.rmtree(transaction_path, ignore_errors=True)
            raise

        SnapshotUtils.cleanup_after_commit([transaction_path], "Snapshot creation")

    def delete(self, message_callback=None):
        """
        Deletes the snapshot's directory from the filesystem.
        The directory is moved to a temporary location before being permanently deleted.
        """
        if self.path_snapshot.exists():
            remove_directory_or_move_to_temp(self.path_snapshot, message_callback=message_callback)

    def update_json_data_fields(self):
        """
        Updates the 'data' and 'date_last_modified' fields in the snapshot's JSON file.
        This method is typically called after modifying the snapshot's data dictionary.
        """
        SnapshotSerializer.update_field(self.path_snapshot_json, "data", self.snapshot.data)
        SnapshotSerializer.update_field(self.path_snapshot_json, "date_last_modified", datetime.now().isoformat())
        self.snapshot.date_last_modified = datetime.now()

    def update_json_base_fields(self):
        """
        Updates the basic metadata fields (name, desc, author, tags, date_modified)
        of the snapshot's JSON file.
        """
        SnapshotSerializer.update_field(self.path_snapshot_json, "name", self.snapshot.name)
        SnapshotSerializer.update_field(self.path_snapshot_json, "desc", self.snapshot.desc)
        SnapshotSerializer.update_field(self.path_snapshot_json, "author", self.snapshot.author)
        SnapshotSerializer.update_field(self.path_snapshot_json, "tags", self.snapshot.tags)
        SnapshotSerializer.update_field(self.path_snapshot_json, "date_modified", datetime.now().isoformat())
        self.snapshot.date_modified = datetime.now()

    def install_directory(self, destination_path: Path):
        """
        Adds a new directory to the snapshot, copying its contents into the
        snapshot's storage directory.

        Args:
            destination_path: The path of the directory to add to the snapshot.

        Raises:
            ValueError: If the destination_path is not a valid directory.
        """
        if not destination_path.exists() or not destination_path.is_dir():
            raise ValueError(f"The provided path {destination_path} is not a valid directory.")
        new_dir = SnapDirAssociation(
            index=SnapDirAssociation.next_index(),
            original_path=destination_path.as_posix(),
            folder_id=gen_random_string(self.settings.folder_id_length),
        )
        new_dir.copy_install_to(self.path_snapshot)
        self.snapshot.directories.append(new_dir)
        self.__save_json()

    def uninstall_directory_by_folder_id(self, folder_id: str):
        """
        Removes a directory from the snapshot based on its folder_id.
        This deletes the directory's copy from the snapshot's storage and updates the JSON file.

        Args:
            folder_id: The unique ID of the folder to remove.
        """
        dir_to_remove = next((d for d in self.snapshot.directories if d.folder_id == folder_id), None)
        if dir_to_remove:
            dir_path = self.path_snapshot.joinpath(dir_to_remove.directory_name)
            if dir_path.exists():
                remove_directory_or_move_to_temp(dir_path)
            self.snapshot.directories.remove(dir_to_remove)
            self.__save_json()

    def update_from_actions_list(self, edits: list[SnapEditAction], message_callback=None):
        """
        Plans edits by association ID against the stored metadata, then stages all
        affected copies before assigning final names. Originals remain available
        for rollback until the updated metadata has been saved.

        Args:
            edits: A list of SnapEditAction objects.
        """
        old_json = self.path_snapshot_json.read_bytes()
        old = SnapshotSerializer.from_json(self.path_snapshot_json)
        expected_edits = SnapshotUtils.get_edits_between_snapshots(old, self.snapshot)
        old_by_id = {assoc.folder_id: assoc for assoc in old.directories}
        new_by_id = {assoc.folder_id: assoc for assoc in self.snapshot.directories}
        for snapshot in (old, self.snapshot):
            names = [assoc.directory_name for assoc in snapshot.directories]
            if len(set(names)) != len(names):
                raise ValueError("Snapshot associations must have unique directory names.")

        # Resolve legacy name/path-based actions against the original metadata,
        # before any name is reused by another association.
        actions_by_id = {}
        for edit in edits:
            folder_id = edit.folder_id or edit.folder_id_to_remove
            if not folder_id:
                if edit.action_type == SnapEditType.ADD_DIR:
                    matches = [assoc for assoc in self.snapshot.directories if assoc.original_path == edit.new_path]
                else:
                    name = edit.old_directory_name or edit.directory_name_to_remove
                    matches = [assoc for assoc in old.directories if assoc.directory_name == name]
                if len(matches) != 1:
                    raise ValueError("Edit action does not identify a unique association.")
                folder_id = matches[0].folder_id
            if folder_id in actions_by_id:
                raise ValueError(f"Multiple edit actions for association '{folder_id}'.")
            actions_by_id[folder_id] = edit.action_type
        if actions_by_id != {edit.folder_id: edit.action_type for edit in expected_edits}:
            raise ValueError("Edit actions do not match the stored and requested snapshot associations.")

        moves = []
        additions = []
        for edit in expected_edits:
            if edit.action_type == SnapEditType.ADD_DIR:
                additions.append(new_by_id[edit.folder_id])
            else:
                source = self.path_snapshot / old_by_id[edit.folder_id].directory_name
                target = self.path_snapshot / new_by_id[edit.folder_id].directory_name if edit.action_type == SnapEditType.RENAME_DIR else None
                moves.append((source, target))

        # Validate the complete plan before touching any stored copy.
        sources = {source for source, _ in moves}
        targets = [target for _, target in moves if target is not None] + [self.path_snapshot / assoc.directory_name for assoc in additions]
        for assoc in old.directories:
            source = self.path_snapshot / assoc.directory_name
            if not source.is_dir():
                raise FileNotFoundError(f"Snapshot directory '{source}' is missing.")
        for target in targets:
            if target.exists() and target not in sources:
                raise FileExistsError(f"Snapshot destination '{target}' is already occupied.")
        for assoc in additions:
            if not Path(assoc.original_path).is_dir():
                raise FileNotFoundError(f"Source directory '{assoc.original_path}' is missing.")

        staging_path = Path(tempfile.mkdtemp(prefix="_staging_update_", dir=self.path_snapshot))
        staged_originals = []
        publications = []
        published = []
        saving_json = False
        try:
            for i, (source, target) in enumerate(moves):
                staged = staging_path / f"original_{i}"
                source.rename(staged)
                staged_originals.append((staged, source))
                if target is not None:
                    publications.append((staged, target))
            for assoc in additions:
                assoc.copy_install_to(staging_path / "additions", message_callback=message_callback)
                publications.append((staging_path / "additions" / assoc.directory_name, self.path_snapshot / assoc.directory_name))

            for staged, target in publications:
                if target.exists():
                    raise FileExistsError(f"Snapshot destination '{target}' is already occupied.")
                staged.rename(target)
                published.append((staged, target))

            for assoc in self.snapshot.directories:
                expected_path = self.path_snapshot / assoc.directory_name
                if not expected_path.is_dir():
                    raise RuntimeError(f"Integrity check failed: Expected snapshot directory '{expected_path}' is missing.")
            saving_json = True
            self.__save_json()
        except Exception:
            for staged, target in reversed(published):
                target.rename(staged)
            for staged, source in reversed(staged_originals):
                staged.rename(source)
            if saving_json:
                self.path_snapshot_json.write_bytes(old_json)
            shutil.rmtree(staging_path)
            raise

        # Deletions only affect staged originals after the new state is committed.
        SnapshotUtils.cleanup_after_commit([staging_path], "Snapshot update")

    def duplicate(self, message_callback=None):
        """
        Creates a duplicate of the current snapshot with a new ID and name.
        The entire snapshot directory is copied, and a new JSON file is created for the copy.

        Raises:
            FileNotFoundError: If the original snapshot path does not exist.
        """
        if not self.path_snapshot.exists():
            raise FileNotFoundError(f"The snapshot path {self.path_snapshot} does not exist.")
        new_snap = self.snapshot.clone()
        new_snap.id = gen_random_string(self.settings.snap_id_length)
        new_snap.name = self.snapshot.name + " Copy"
        new_snap.date_created = datetime.now()
        new_snap_path = SnapshotUtils.get_snapshot_path(new_snap.folder_name, self.path_catalogue)
        new_snap_json_path = SnapshotUtils.get_snapshot_json_path(new_snap.folder_name, self.path_catalogue, self.settings.json_filename)
        duplicate_directory(self.path_snapshot, new_snap_path, "", message_callback=message_callback)
        SnapshotSerializer.to_json(new_snap, new_snap_json_path)

    def update_associated_dirs_from_system(self, message_callback=None):
        """
        Updates the snapshot's internal copy of each associated directory
        with the current version from the original system path.
        """
        # 1 & 2. Validate all sources before deleting anything
        for dir_assoc in self.snapshot.directories:
            system_path = Path(dir_assoc.original_path)
            if not system_path.exists() or not system_path.is_dir():
                raise FileNotFoundError(f"Original path '{system_path}' for snapshot '{self.snapshot.id}' does not exist or is not a directory. Update aborted.")

        rollbacks = []
        try:
            for dir_assoc in self.snapshot.directories:
                system_path = Path(dir_assoc.original_path)
                snapshot_copy_path = self.path_snapshot / dir_assoc.directory_name

                # 4. Copy each source to staging
                staging_dir = self.path_snapshot / f"{dir_assoc.directory_name}_staging_{gen_random_string(6)}"
                backup_dir = self.path_snapshot / f"{dir_assoc.directory_name}_bck_{gen_random_string(6)}"

                logger.info(f"Copying '{system_path}' to staging '{staging_dir}'")

                def copy_with_cb(src, dst, *, follow_symlinks=True):
                    if message_callback:
                        message_callback(f"Copia in corso: {Path(src).name}")
                    shutil.copy2(src, dst, follow_symlinks=follow_symlinks)

                try:
                    shutil.copytree(system_path, staging_dir, copy_function=copy_with_cb)
                except Exception as e:
                    if staging_dir.exists():
                        shutil.rmtree(staging_dir)
                    raise RuntimeError(f"Failed to copy system path '{system_path}' to staging '{staging_dir}': {e}") from e

                rollbacks.append(
                    {
                        "snapshot_copy_path": snapshot_copy_path,
                        "staging_dir": staging_dir,
                        "backup_dir": backup_dir,
                        "dir_assoc": dir_assoc,
                        "system_path": system_path,
                    }
                )

            # Replace internal copy only at the end
            for rb in rollbacks:
                snap_path = rb["snapshot_copy_path"]
                staging_dir = rb["staging_dir"]
                backup_dir = rb["backup_dir"]

                if snap_path.exists():
                    snap_path.rename(backup_dir)

                staging_dir.rename(snap_path)

            # Update metadata while backups are still intact.
            for rb in rollbacks:
                dir_assoc = rb["dir_assoc"]
                dir_assoc.mb_size = get_folder_size_mb(rb["system_path"])

        except Exception as e:
            logger.error(f"Update from system failed during transaction. Rolling back. Reason: {e}")
            for rb in rollbacks:
                snap_path = rb["snapshot_copy_path"]
                staging_dir = rb["staging_dir"]
                backup_dir = rb["backup_dir"]

                if staging_dir.exists():
                    shutil.rmtree(staging_dir)

                if backup_dir.exists():
                    if snap_path.exists():
                        shutil.rmtree(snap_path)
                    backup_dir.rename(snap_path)
            raise

        self.snapshot.date_last_modified = datetime.now()
        self.__save_json()
        SnapshotUtils.cleanup_after_commit((rb["backup_dir"] for rb in rollbacks), "Update from system")

    def remove_installed_copies(self, message_callback=None):
        """
        Removes all directories on the system that this snapshot is managing.
        This is effectively an 'uninstall' operation for the snapshot's associated directories.
        It only removes the copies at the 'original_path' locations, not the snapshot's
        internal backup.
        """
        for dir_assoc in self.snapshot.directories:
            install_path = Path(dir_assoc.original_path)

            if is_critical_system_path(install_path):
                raise ValueError(f"Cannot remove installed copy at '{install_path}': it is a critical system path.")

            if install_path.exists() and install_path.is_dir():
                logger.info(f"Removing installed copy at '{install_path}'")
                try:
                    remove_directory_or_move_to_temp(install_path, message_callback=message_callback)
                except Exception as e:
                    logger.error(f"Failed to remove directory '{install_path}': {e}")
            else:
                logger.debug(f"Install path '{install_path}' does not exist or is not a directory. Skipping.")

    def install(self, enable_everyone_full_control: bool = True, clear_destination: bool = True, progress_callback=None, message_callback=None):
        """
        Installs the snapshot's contents to their original locations on the filesystem.
        This will clear the destination directories before copying the snapshot's contents.

        Args:
            enable_everyone_full_control (bool): If True and on Windows, it will attempt
                to set full control permissions for the 'Everyone' group on the
                installed directories.
            clear_destination (bool): If True, clears the destination directories before copying.
        """
        import os
        import platform
        import sys

        if self.snapshot.os_created and self.snapshot.os_created != platform.system():
            raise RuntimeError(f"Cannot install snapshot: created on {self.snapshot.os_created}, but current OS is {platform.system()}.")

        if sys.platform == "win32":
            try:
                import ntsecuritycon as con
                import win32security
            except ImportError:
                logger.error("pywin32 not installed, cannot set file permissions.")
                win32security = None
        else:
            win32security = None

        total_dirs = len(self.snapshot.directories)

        # 1. Preflight
        for dir_assoc in self.snapshot.directories:
            source_dir = self.path_snapshot.joinpath(dir_assoc.directory_name)
            if not source_dir.exists() or not source_dir.is_dir():
                raise FileNotFoundError(f"Source directory '{source_dir}' does not exist inside the snapshot.")
            install_location = Path(dir_assoc.original_path)
            if is_critical_system_path(install_location):
                raise ValueError(f"Cannot install to '{install_location}': it is a critical system path.")

        rollbacks = []
        try:
            for i, dir_assoc in enumerate(self.snapshot.directories):
                source_dir = self.path_snapshot.joinpath(dir_assoc.directory_name)
                install_location = Path(dir_assoc.original_path)

                # 2. Copiare in una directory temporanea (Staging)
                staging_dir = install_location.with_name(f"{install_location.name}_staging_{gen_random_string(6)}")
                backup_dir = install_location.with_name(f"{install_location.name}_bck_{gen_random_string(6)}")

                total_bytes = 0
                if progress_callback:
                    total_bytes = sum(f.stat().st_size for f in source_dir.rglob("*") if f.is_file())
                copied_bytes = [0]

                def copy_with_prog(src, dst, *, follow_symlinks=True):
                    if message_callback:
                        message_callback(f"Copia in corso: {Path(src).name}")
                    shutil.copy2(src, dst, follow_symlinks=follow_symlinks)
                    if progress_callback:
                        copied_bytes[0] += os.path.getsize(src)
                        dir_pct = (copied_bytes[0] / total_bytes) if total_bytes > 0 else 1.0
                        overall_pct = ((i + dir_pct) / total_dirs) * 100
                        progress_callback(int(overall_pct))

                logger.info(f"Copying '{source_dir}' to staging '{staging_dir}'")
                try:
                    shutil.copytree(source_dir, staging_dir, copy_function=copy_with_prog)
                except Exception as e:
                    if staging_dir.exists():
                        shutil.rmtree(staging_dir)
                    raise RuntimeError(f"Failed to copy to staging '{staging_dir}': {e}") from e

                # 3. Se copytree termina senza eccezioni, l'operazione è integra (non catturiamo errori per singoli file)

                rollbacks.append({"install_loc": install_location, "staging_dir": staging_dir, "backup_dir": backup_dir})

            # 4. Sostituire la destinazione soltanto dopo il completamento di tutti gli staging
            for rb in rollbacks:
                install_loc = rb["install_loc"]
                staging_dir = rb["staging_dir"]
                backup_dir = rb["backup_dir"]

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

            if win32security:
                for rb in rollbacks:
                    install_loc = rb["install_loc"]
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

        except Exception as e:
            # 5. Ripristinare la vecchia directory se lo swap fallisce
            logger.error(f"Installation failed during transaction. Rolling back. Reason: {e}")
            for rb in rollbacks:
                install_loc = rb["install_loc"]
                staging_dir = rb["staging_dir"]
                backup_dir = rb["backup_dir"]

                if staging_dir.exists():
                    shutil.rmtree(staging_dir)

                if clear_destination and backup_dir.exists():
                    if install_loc.exists():
                        shutil.rmtree(install_loc)
                    backup_dir.rename(install_loc)
            raise

        # 7. Aggiornare `date_last_used` soltanto dopo commit riuscito
        self.snapshot.date_last_used = datetime.now()
        SnapshotSerializer.update_field(
            self.path_snapshot_json,
            "date_last_used",
            self.snapshot.date_last_used.isoformat(),
        )
        SnapshotUtils.cleanup_after_commit((path for rb in rollbacks for path in (rb["backup_dir"], rb["staging_dir"])), "Installation")

    def create_backup(self, backup_path: Path, prefix: str, backup_type: "BackupType", is_export: bool = False, message_callback=None):
        """
        Creates a zip archive of the snapshot's data.

        Args:
            backup_path: The directory where the backup zip file will be saved.
            prefix: A prefix for the backup filename.
            backup_type: The type of backup to create (associated directories or the snapshot directory).
            is_export: If True, the filename will be formatted as an export.
        """
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            backup_type_suffix = ""
            if backup_type == BackupType.ASSOCIATED_DIRECTORIES:
                backup_type_suffix = "_ad"
            elif backup_type == BackupType.SNAPSHOT_DIRECTORY:
                backup_type_suffix = "_sd"

            if is_export:
                zip_name = f"{prefix}_{self.snapshot.id}{backup_type_suffix}_{timestamp}.zip"
            else:
                zip_name = f"backup_{prefix}_{self.snapshot.id}{backup_type_suffix}_{timestamp}.zip"

            backup_path.mkdir(parents=True, exist_ok=True)
            zip_path = backup_path.joinpath(zip_name)

            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
                if backup_type == BackupType.ASSOCIATED_DIRECTORIES:
                    for d in self.snapshot.directories:
                        folder = Path(d.original_path)
                        if folder.is_dir():
                            for file_path in folder.rglob("*"):
                                if file_path.is_file():
                                    if message_callback:
                                        message_callback(f"Archiviazione: {file_path.name}")
                                    archive.write(
                                        file_path,
                                        arcname=os.path.join(d.directory_name, file_path.relative_to(folder)),
                                    )
                elif backup_type == BackupType.SNAPSHOT_DIRECTORY:
                    source_dir = self.path_snapshot
                    for file_path in source_dir.rglob("*"):
                        if file_path.is_file():
                            if message_callback:
                                message_callback(f"Archiviazione: {file_path.name}")
                            archive.write(file_path, arcname=file_path.relative_to(source_dir))
        except Exception as e:
            logger.error(e)
