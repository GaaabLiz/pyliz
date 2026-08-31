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
import zipfile
from datetime import datetime
from pathlib import Path

from pylizlib.core.data.gen import gen_random_string
from pylizlib.core.log.pylizLogger import logger
from pylizlib.core.os.path import clear_folder_contents, clear_or_move_to_temp, duplicate_directory
from pylizlib.core.os.utils import get_folder_size_mb, is_critical_system_path
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

    def create(self, progress_callback=None):
        """
        Creates the snapshot on the filesystem. This involves creating the main snapshot
        directory and copying all associated directories into it. If the directory
        already exists, its contents are cleared first.
        """
        if self.path_snapshot.exists():
            clear_folder_contents(self.path_snapshot)
        self.path_snapshot.mkdir(parents=True, exist_ok=True)
        
        # We need to distribute the progress among directories if there are multiple.
        total_dirs = len(self.snapshot.directories)
        for i, snap_dir in enumerate(self.snapshot.directories):
            def dir_progress(copied, total):
                if progress_callback:
                    # Calculate overall percentage based on dir index and dir progress
                    dir_pct = (copied / total) if total > 0 else 1.0
                    overall_pct = ((i + dir_pct) / total_dirs) * 100
                    progress_callback(int(overall_pct))
                    
            snap_dir.copy_install_to(self.path_snapshot, progress_callback=dir_progress)
        self.__save_json()

    def delete(self):
        """
        Deletes the snapshot's directory from the filesystem.
        The directory is moved to a temporary location before being permanently deleted.
        """
        if self.path_snapshot.exists():
            clear_or_move_to_temp(self.path_snapshot)

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
                clear_or_move_to_temp(dir_path)
            self.snapshot.directories.remove(dir_to_remove)
            self.__save_json()

    def update_from_actions_list(self, edits: list[SnapEditAction]):
        """
        Applies a list of edit actions (add/remove directories) to the snapshot.
        This updates the snapshot's contents on the filesystem based on the provided actions.

        Args:
            edits: A list of SnapEditAction objects.
        """
        # The `self.snapshot` is the NEW snapshot.

        # Handle additions
        add_actions = [e for e in edits if e.action_type == SnapEditType.ADD_DIR]
        added_paths = {e.new_path for e in add_actions}

        for dir_assoc in self.snapshot.directories:
            # Find the newly added directories in the snapshot's list
            # The path in dir_assoc is already normalized by __post_init__
            if dir_assoc.original_path in added_paths:
                # This is a new directory. Copy its content to the snapshot storage.
                dir_assoc.copy_install_to(self.path_snapshot)

        # Handle removals
        remove_actions = [e for e in edits if e.action_type == SnapEditType.REMOVE_DIR]
        for edit in remove_actions:
            if edit.directory_name_to_remove:
                dir_path = self.path_snapshot.joinpath(edit.directory_name_to_remove)
                if dir_path.exists():
                    clear_or_move_to_temp(dir_path)

        # After all filesystem changes, save the final state of the new snapshot.
        self.__save_json()

    def duplicate(self):
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
        duplicate_directory(self.path_snapshot, new_snap_path, "")
        SnapshotSerializer.to_json(new_snap, new_snap_json_path)

    def update_associated_dirs_from_system(self):
        """
        Updates the snapshot's internal copy of each associated directory
        with the current version from the original system path.
        """
        for dir_assoc in self.snapshot.directories:
            snapshot_copy_path = self.path_snapshot / dir_assoc.directory_name
            system_path = Path(dir_assoc.original_path)

            if snapshot_copy_path.exists():
                shutil.rmtree(snapshot_copy_path)

            if system_path.exists() and system_path.is_dir():
                dir_assoc.copy_install_to(self.path_snapshot)
                dir_assoc.mb_size = get_folder_size_mb(system_path)
            else:
                dir_assoc.mb_size = 0.0
                logger.warning(f"Original path '{system_path}' for snapshot '{self.snapshot.id}' does not exist. The snapshot's copy has been cleared.")

        self.snapshot.date_last_modified = datetime.now()
        self.__save_json()

    def remove_installed_copies(self):
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
                    shutil.rmtree(install_path)
                except Exception as e:
                    logger.error(f"Failed to remove directory '{install_path}': {e}")
            else:
                logger.debug(f"Install path '{install_path}' does not exist or is not a directory. Skipping.")

    def install(self, enable_everyone_full_control: bool = True, clear_destination: bool = True, progress_callback=None):
        """
        Installs the snapshot's contents to their original locations on the filesystem.
        This will clear the destination directories before copying the snapshot's contents.

        Args:
            enable_everyone_full_control (bool): If True and on Windows, it will attempt
                to set full control permissions for the 'Everyone' group on the
                installed directories.
            clear_destination (bool): If True, clears the destination directories before copying.
        """
        import sys
        import os
        import platform

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
                    total_bytes = sum(f.stat().st_size for f in source_dir.rglob('*') if f.is_file())
                copied_bytes = [0]
                
                def copy_with_prog(src, dst, *, follow_symlinks=True):
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
                
                rollbacks.append({
                    "install_loc": install_location,
                    "staging_dir": staging_dir,
                    "backup_dir": backup_dir
                })

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
                    shutil.rmtree(staging_dir)

            # Cleanup: delete backups on success
            for rb in rollbacks:
                backup_dir = rb["backup_dir"]
                if backup_dir.exists():
                    shutil.rmtree(backup_dir)
                    
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

    def create_backup(
        self,
        backup_path: Path,
        prefix: str,
        backup_type: "BackupType",
        is_export: bool = False,
    ):
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
                    dirs_to_backup = [Path(d.original_path) for d in self.snapshot.directories]
                    for folder in dirs_to_backup:
                        if folder.is_dir():
                            for file_path in folder.rglob("*"):
                                if file_path.is_file():
                                    archive.write(
                                        file_path,
                                        arcname=os.path.join(folder.name, file_path.relative_to(folder)),
                                    )
                elif backup_type == BackupType.SNAPSHOT_DIRECTORY:
                    source_dir = self.path_snapshot
                    for file_path in source_dir.rglob("*"):
                        if file_path.is_file():
                            archive.write(file_path, arcname=file_path.relative_to(source_dir))
        except Exception as e:
            logger.error(e)
