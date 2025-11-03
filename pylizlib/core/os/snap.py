import json
import os
import re
import shutil
import zipfile
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import ClassVar, Optional, Callable

from pylizlib.core.data.gen import gen_random_string
from pylizlib.core.log.pylizLogger import logger
from pylizlib.core.os.path import random_subfolder, clear_folder_contents, clear_or_move_to_temp, duplicate_directory


SnapshotProgressCallback = Callable[[str, int, int], None]


@dataclass
class SnapDirAssociation:
    index: int
    original_path: str
    folder_id: str
    _current_index: ClassVar[int] = 0

    def __post_init__(self):
        self.original_path = Path(self.original_path).as_posix()

    @classmethod
    def next_index(cls):
        cls._current_index += 1
        return cls._current_index

    @property
    def directory_name(self) -> str:
        return self.index.__str__() + "-" + Path(self.original_path).name


    @staticmethod
    def gen_random(source_folder_for_choices: Path, folder_id_length: int = 4) -> 'SnapDirAssociation':
        return SnapDirAssociation(
            index=SnapDirAssociation.next_index(),
            original_path=random_subfolder(source_folder_for_choices).__str__(),
            folder_id=gen_random_string(folder_id_length)
        )

    @staticmethod
    def gen_random_list(count: int, source_folder_for_choices: Path) -> list['SnapDirAssociation']:
        return [SnapDirAssociation.gen_random(source_folder_for_choices) for _ in range(count)]


    def copy_install_to(self, catalogue_target_path: Path):
        source = Path(self.original_path)
        destination = catalogue_target_path.joinpath(self.directory_name)
        destination.mkdir(parents=True, exist_ok=True)

        for src_path in source.iterdir():
            dst_path = destination / src_path.name
            if src_path.is_dir():
                shutil.copytree(src_path, dst_path)
            else:
                shutil.copy2(src_path, dst_path)


class SnapEditType(Enum):
    ADD_DIR = "Add"
    REMOVE_DIR = "Remove"


class SnapshotSortKey(Enum):
    ID = "id"
    NAME = "name"
    DESCRIPTION = "desc"
    AUTHOR = "author"
    DATE_CREATED = "date_created"
    DATE_MODIFIED = "date_modified"
    DATE_LAST_USED = "date_last_used"
    DATE_LAST_MODIFIED = "date_last_modified"


@dataclass
class SnapEditAction:
    action_type: SnapEditType
    timestamp: datetime = datetime.now()
    new_path: str = ""
    folder_id_to_remove: str = ""
    directory_name_to_remove: str = ""


@dataclass
class SnapshotSettings:
    json_filename: str = "snapshot.json"
    backup_path: Path | None = None
    backup_pre_install: bool = False
    backup_pre_modify: bool = False
    backup_pre_delete: bool = False
    install_with_everyone_full_control: bool = True
    snap_id_length: int = 20
    folder_id_length: int = 6

    @property
    def bck_before_install_enabled(self) -> bool:
        return self.backup_pre_install and self.backup_path is not None

    @property
    def bck_before_modify_enabled(self) -> bool:
        return self.backup_pre_modify and self.backup_path is not None

    @property
    def bck_before_delete_enabled(self) -> bool:
        return self.backup_pre_delete and self.backup_path is not None


@dataclass
class Snapshot:
    id: str
    name: str
    desc: str
    author: str = field(default="UnknownUser")
    directories: list[SnapDirAssociation] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    date_created: datetime = datetime.now()
    date_modified: datetime | None = None
    date_last_used: datetime | None = None
    date_last_modified: datetime | None = None
    data: dict[str, str] = field(default_factory=dict)

    @property
    def tags_as_string(self) -> str:
        return ", ".join(self.tags) if self.tags else " "

    def get_for_table_array(self, key_list: list[str]) -> list[str]:
        array = [self.name, self.desc]
        for key in key_list:
            value = self.data.get(key, "")
            array.append(value)
        array.append(self.date_created.strftime("%d/%m/%Y %H:%M:%S"))
        array.append(self.tags_as_string)
        return array

    @property
    def folder_name(self) -> str:
        return self.id

    def add_data_item(self, key: str, value: str) -> None:
        """Aggiunge un elemento al dizionario."""
        self.data[key] = value

    def remove_data_item(self, key: str) -> Optional[str]:
        """Rimuove un elemento dal dizionario e restituisce il valore rimosso."""
        return self.data.pop(key, None)

    def has_data_item(self, key: str) -> bool:
        """Verifica se una chiave esiste nel dizionario."""
        return key in self.data

    def get_data_item(self, key: str, default: str = "") -> str:
        """Ottiene un valore dal dizionario con un default."""
        return self.data.get(key, default)

    def clear_all_data(self) -> None:
        """Pulisce tutti gli elementi del dizionario."""
        self.data.clear()

    def edit_data_item(self, key: str, new_value: str) -> None:
        """Modifica il valore di un elemento esistente nel dizionario."""
        if key in self.data:
            self.data[key] = new_value
        else:
            raise KeyError(f"Key '{key}' not found in data.")


    def clone(self) -> 'Snapshot':
        """Crea una copia profonda dell'istanza Snapshot."""
        return Snapshot(
            id=self.id,
            name=self.name,
            desc=self.desc,
            author=self.author,
            directories=[SnapDirAssociation(
                index=dir_assoc.index,
                original_path=dir_assoc.original_path,
                folder_id=dir_assoc.folder_id
            ) for dir_assoc in self.directories],
            tags=list(self.tags),
            date_created=self.date_created,
            date_modified=self.date_modified,
            date_last_used=self.date_last_used,
            date_last_modified=self.date_last_modified,
            data=dict(self.data)
        )












class SnapshotUtils:

    @staticmethod
    def gen_random_snap(source_folder_for_choices: Path, id_length: int = 10, ) -> Snapshot:
        dirs = SnapDirAssociation.gen_random_list(3, source_folder_for_choices)
        return Snapshot(
            id=gen_random_string(id_length),
            name="Snapshot " + gen_random_string(id_length),
            desc="Randomly generated snapshot",
            author="User",
            directories=dirs,
            tags=["example", "test"],
        )


    @staticmethod
    def get_snapshot_from_path(path_snapshot: Path, json_filename: str) -> Snapshot | None:
        if path_snapshot.is_file():
            raise ValueError(f"The provided path {path_snapshot} is not a directory.")
        if not path_snapshot.exists():
            raise FileNotFoundError(f"The provided path {path_snapshot} does not exist.")
        path_snapshot_json = path_snapshot.joinpath(json_filename)
        if not path_snapshot_json.is_file():
            raise FileNotFoundError(f"No snapshot.json file found in {path_snapshot}.")
        return SnapshotSerializer.from_json(path_snapshot_json)

    @staticmethod
    def get_snapshot_path(folder_name: str, catalogue_path: Path) -> Path:
        return catalogue_path.joinpath(folder_name)

    @staticmethod
    def get_snapshot_json_path(folder_name: str, catalogue_path: Path, json_filename: str) -> Path:
        return SnapshotUtils.get_snapshot_path(folder_name, catalogue_path).joinpath(json_filename)

    @staticmethod
    def get_edits_between_snapshots(old: Snapshot, new: Snapshot) -> list[SnapEditAction]:
        edits: list[SnapEditAction] = []

        old_path_to_assoc = {dir_assoc.original_path: dir_assoc for dir_assoc in old.directories}
        new_path_to_assoc = {dir_assoc.original_path: dir_assoc for dir_assoc in new.directories}

        old_paths = set(old_path_to_assoc.keys())
        new_paths = set(new_path_to_assoc.keys())

        # Trova cartelle aggiunte (presenti in new ma non in old)
        added_paths = new_paths - old_paths
        for path in added_paths:
            edits.append(SnapEditAction(
                action_type=SnapEditType.ADD_DIR,
                new_path=path
            ))

        # Trova cartelle rimosse (presenti in old ma non in new)
        removed_paths = old_paths - new_paths
        for path in removed_paths:
            assoc = old_path_to_assoc[path]
            edits.append(SnapEditAction(
                action_type=SnapEditType.REMOVE_DIR,
                folder_id_to_remove=assoc.folder_id,
                directory_name_to_remove=assoc.directory_name
            ))

        return edits

    @staticmethod
    def sort_snapshots(
        snapshots: list[Snapshot],
        sort_by: 'SnapshotSortKey',
        reverse: bool = False
    ) -> list[Snapshot]:
        """
        Sorts a list of Snapshot objects by a specified key.
        Snapshots with a None value for the key are placed at the end.
        String comparison is case-insensitive.

        Args:
            snapshots: The list of Snapshots to sort.
            sort_by: The key to sort by, as a SnapshotSortKey enum member.
            reverse: If True, sorts in descending order.

        Returns:
            A new list containing the sorted Snapshots.
        """
        key_attr = sort_by.value
        snaps_with_value = []
        snaps_with_none = []

        for snap in snapshots:
            if getattr(snap, key_attr) is None:
                snaps_with_none.append(snap)
            else:
                snaps_with_value.append(snap)

        def get_key(snapshot: Snapshot):
            value = getattr(snapshot, key_attr)
            if isinstance(value, str):
                return value.lower()
            return value

        sorted_snaps = sorted(snaps_with_value, key=get_key, reverse=reverse)

        return sorted_snaps + snaps_with_none




class SnapshotSerializer:

    @staticmethod
    def _converter(o):
        """Converti datetime e enum in formati serializzabili JSON."""
        if isinstance(o, datetime):
            return o.isoformat()
        if isinstance(o, Enum):
            return o.value  # oppure o.name se preferisci il nome
        raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")

    @staticmethod
    def to_json(snapshot: Snapshot, path: Path) -> None:
        data_dict = asdict(snapshot)
        json_str = json.dumps(data_dict, default=SnapshotSerializer._converter, indent=4)
        path.write_text(json_str, encoding="utf-8")


    @classmethod
    def from_json(cls, filepath: Path) -> Snapshot:
        """Legge un AtomDevConfig da file JSON, convertendo datetime ed enum"""
        data = json.loads(filepath.read_text(encoding="utf-8"))

        # Converte i campi datetime da stringa ISO8601 a datetime
        for key in ["date_created", "date_last_installed", "date_modified", "date_last_used", "date_last_modified"]:
            if key in data and data[key] is not None:
                data[key] = datetime.fromisoformat(data[key])

        # Conversione 'directories' in lista di ConfigDirAssociation
        if "directories" in data and isinstance(data["directories"], list):
            data["directories"] = [SnapDirAssociation(**d) if isinstance(d, dict) else d for d in data["directories"]]

        return Snapshot(**data)

    @classmethod
    def update_field(cls, filepath: Path, field_name: str, new_value):
        # Leggi dati esistenti dal file JSON
        data = json.loads(filepath.read_text(encoding="utf-8"))

        # Aggiorna solo il campo specificato
        data[field_name] = new_value

        # Serializza di nuovo il file con i convertitori per datetime e enum se necessario
        json_str = json.dumps(data, default=cls._converter, indent=4)
        filepath.write_text(json_str, encoding="utf-8")



class SnapshotManager:

    def __init__(
            self,
            snapshot: Snapshot,
            catalogue_path: Path,
            settings: SnapshotSettings = SnapshotSettings(),
    ):
        self.snapshot = snapshot
        self.settings = settings
        self.path_catalogue = catalogue_path
        self.path_snapshot = SnapshotUtils.get_snapshot_path(self.snapshot.folder_name, self.path_catalogue)
        self.path_snapshot_json = SnapshotUtils.get_snapshot_json_path(self.snapshot.folder_name, self.path_catalogue, self.settings.json_filename)

    def __save_json(self):
        SnapshotSerializer.to_json(self.snapshot, self.path_snapshot_json)

    def create(self):
        if self.path_snapshot.exists():
            clear_folder_contents(self.path_snapshot)
        self.path_snapshot.mkdir(parents=True, exist_ok=True)
        for snap_dir in self.snapshot.directories:
            snap_dir.copy_install_to(self.path_snapshot)
        self.__save_json()

    def delete(self):
        if self.path_snapshot.exists():
            clear_or_move_to_temp(self.path_snapshot)

    def update_json_data_fields(self):
        SnapshotSerializer.update_field(self.path_snapshot_json, "data", self.snapshot.data)
        SnapshotSerializer.update_field(self.path_snapshot_json, "date_last_modified", datetime.now().isoformat())
        self.snapshot.date_last_modified = datetime.now()

    def update_json_base_fields(self):
        SnapshotSerializer.update_field(self.path_snapshot_json, "name", self.snapshot.name)
        SnapshotSerializer.update_field(self.path_snapshot_json, "desc", self.snapshot.desc)
        SnapshotSerializer.update_field(self.path_snapshot_json, "author", self.snapshot.author)
        SnapshotSerializer.update_field(self.path_snapshot_json, "tags", self.snapshot.tags)
        SnapshotSerializer.update_field(self.path_snapshot_json, "date_modified", datetime.now().isoformat())
        self.snapshot.date_modified = datetime.now()

    def install_directory(self, destination_path: Path):
        if not destination_path.exists() or not destination_path.is_dir():
            raise ValueError(f"The provided path {destination_path} is not a valid directory.")
        new_dir = SnapDirAssociation(
            index=SnapDirAssociation.next_index(),
            original_path=destination_path.as_posix(),
            folder_id=gen_random_string(self.settings.folder_id_length)
        )
        new_dir.copy_install_to(self.path_snapshot)
        self.snapshot.directories.append(new_dir)
        self.__save_json()

    def uninstall_directory_by_folder_id(self, folder_id: str):
        dir_to_remove = next((d for d in self.snapshot.directories if d.folder_id == folder_id), None)
        if dir_to_remove:
            dir_path = self.path_snapshot.joinpath(dir_to_remove.directory_name)
            if dir_path.exists():
                clear_or_move_to_temp(dir_path)
            self.snapshot.directories.remove(dir_to_remove)
            self.__save_json()

    def update_from_actions_list(self, edits: list[SnapEditAction]):
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
        if not self.path_snapshot.exists():
            raise FileNotFoundError(f"The snapshot path {self.path_snapshot} does not exist.")
        new_snap = self.snapshot
        new_snap.id = gen_random_string(self.settings.snap_id_length)
        new_snap.name = self.snapshot.name + " Copy"
        new_snap.date_created = datetime.now()
        new_snap_path = SnapshotUtils.get_snapshot_path(new_snap.folder_name, self.path_catalogue)
        new_snap_json_path = SnapshotUtils.get_snapshot_json_path(new_snap.folder_name, self.path_catalogue, self.settings.json_filename)
        duplicate_directory(self.path_snapshot, new_snap_path, "")
        SnapshotSerializer.to_json(new_snap, new_snap_json_path)

    def install(self, enable_everyone_full_control: bool = True):
        import sys
        if sys.platform == 'win32':
            try:
                import win32security
                import ntsecuritycon as con
            except ImportError:
                logger.error("pywin32 not installed, cannot set file permissions.")
                win32security = None
        else:
            win32security = None

        for dir_assoc in self.snapshot.directories:
            source_dir = self.path_snapshot.joinpath(dir_assoc.directory_name)
            install_location = Path(dir_assoc.original_path)

            logger.info(f"Performing clean installation from '{source_dir}' to '{install_location}'")

            # 1. Ensure the destination directory exists.
            install_location.mkdir(parents=True, exist_ok=True)

            # 2. Clear the contents of the destination directory.
            logger.info(f"Clearing contents of '{install_location}' before install.")
            for item in install_location.iterdir():
                try:
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
                except Exception as e:
                    logger.error(f"Could not remove item {item} during clean install: {e}")

            # 3. Copy the contents from the source directory to the now-empty destination.
            for item in source_dir.iterdir():
                src_item = source_dir / item.name
                dst_item = install_location / item.name
                try:
                    if src_item.is_dir():
                        shutil.copytree(src_item, dst_item)
                    else:
                        shutil.copy2(src_item, dst_item)
                except Exception as e:
                    logger.error(f"Could not copy item {src_item} during install: {e}")

            # 4. Set permissions if on Windows and pywin32 is installed
            if win32security:
                try:
                    logger.info(f"Setting full control permissions for Everyone on '{install_location}'")

                    everyone, domain, type = win32security.LookupAccountName("", "Everyone")

                    sd = win32security.GetFileSecurity(str(install_location), win32security.DACL_SECURITY_INFORMATION)
                    dacl = sd.GetSecurityDescriptorDacl()

                    dacl.AddAccessAllowedAceEx(
                        win32security.ACL_REVISION,
                        con.OBJECT_INHERIT_ACE | con.CONTAINER_INHERIT_ACE,
                        con.GENERIC_ALL,
                        everyone
                    )

                    sd.SetSecurityDescriptorDacl(1, dacl, 0)
                    win32security.SetFileSecurity(str(install_location), win32security.DACL_SECURITY_INFORMATION, sd)

                except Exception as e:
                    logger.error(f"Failed to set permissions on '{install_location}': {e}")

        self.snapshot.date_last_used = datetime.now()
        SnapshotSerializer.update_field(self.path_snapshot_json, "date_last_used", self.snapshot.date_last_used.isoformat())

    def backup_associated(self, prefix: str, backup_path: Path):
        try:
            dirs_to_backup = list(self.snapshot.directories)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            zip_name = f"backup_{prefix}_{self.snapshot.id}_{timestamp}.zip"
            backup_path.mkdir(parents=True, exist_ok=True)
            zip_path = backup_path.joinpath(zip_name)
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
                for folder in dirs_to_backup:
                    folder = Path(folder.original_path)
                    if folder.is_dir():
                        for file_path in folder.rglob("*"):
                            # Evita di includere la directory vuota
                            if file_path.is_file():
                                # Archivia la struttura originale relativa alla directory base
                                archive.write(
                                    file_path,
                                    arcname=os.path.join(folder.name, file_path.relative_to(folder))
                                )
        except Exception as e:
            logger.error(e)


    def backup_snap_directory(self, backup_path: Path):
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            zip_name = f"backup_snapdir_{self.snapshot.id}_{timestamp}.zip"
            backup_path.mkdir(parents=True, exist_ok=True)
            zip_path = backup_path.joinpath(zip_name)
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
                for file_path in self.path_snapshot.rglob("*"):
                    # Evita di includere la directory vuota
                    if file_path.is_file():
                        # Archivia la struttura originale relativa alla directory base
                        archive.write(
                            file_path,
                            arcname=file_path.relative_to(self.path_snapshot)
                        )
        except Exception as e:
            logger.error(e)

class SnapshotCatalogue:

    def __init__(
            self,
            path_catalogue: Path,
            settings: SnapshotSettings = SnapshotSettings(),
    ):
        self.path_catalogue = path_catalogue
        self.settings = settings
        self.path_catalogue.mkdir(parents=True, exist_ok=True)

    def set_catalogue_path(self, new_path: Path):
        self.path_catalogue = new_path
        self.path_catalogue.mkdir(parents=True, exist_ok=True)

    def add(self, snap: Snapshot):
        snap_manager = SnapshotManager(snap, self.path_catalogue, self.settings)
        snap_manager.create()

    def delete(self, snap: Snapshot):
        snap_manager = SnapshotManager(snap, self.path_catalogue, self.settings)
        if self.settings.bck_before_delete_enabled:
            snap_manager.backup_snap_directory(self.settings.backup_path)
        snap_manager.delete()

    def get_all(self) -> list[Snapshot]:
        self.path_catalogue.mkdir(parents=True, exist_ok=True)
        snapshots: list[Snapshot] = []
        for current_dir in self.path_catalogue.iterdir():
            if current_dir.is_dir():
                snap = SnapshotUtils.get_snapshot_from_path(current_dir, self.settings.json_filename)
                if snap is not None:
                    snapshots.append(snap)
        return snapshots

    def get_by_id(self, snap_id: str) -> Optional[Snapshot]:
        all_snaps = self.get_all()
        for snap in all_snaps:
            if snap.id == snap_id:
                return snap
        return None

    def update_snapshot_by_objs(self, old: Snapshot, new: Snapshot):
        edits = SnapshotUtils.get_edits_between_snapshots(old, new)
        self.update_snapshot_by_edits(new, edits)

    def update_snapshot_by_edits(self, snap: Snapshot, edits: list[SnapEditAction]):
        snap_manager = SnapshotManager(snap, self.path_catalogue, self.settings)
        if self.settings.bck_before_modify_enabled:
            snap_manager.backup_snap_directory(self.settings.backup_path)
        snap_manager.update_json_base_fields()
        snap_manager.update_json_data_fields()
        snap_manager.update_from_actions_list(edits)

    def duplicate_by_id(self, snap_id: str):
        snap = self.get_by_id(snap_id)
        if snap is None:
            raise ValueError(f"No snapshot found with ID {snap_id}")
        snap_manager = SnapshotManager(snap, self.path_catalogue, self.settings)
        snap_manager.duplicate()

    def install(self, snap: Snapshot):
        snap_manager = SnapshotManager(snap, self.path_catalogue, self.settings)
        if self.settings.bck_before_install_enabled:
            snap_manager.backup_associated("preinstall", self.settings.backup_path)
        snap_manager.install(self.settings.install_with_everyone_full_control)

    def exists(self, snap_id: str) -> bool:
        return self.get_by_id(snap_id) is not None

    def get_snap_directory_path(self, snap: Snapshot) -> Path | None:
        if not self.exists(snap.id):
            return None
        return SnapshotUtils.get_snapshot_path(snap.folder_name, self.path_catalogue)


@dataclass
class SnapshotSearchResult:
    """
    Rappresenta un singolo risultato di ricerca all'interno di un file di snapshot.
    """
    file_path: Path
    searched_text: str
    line_number: int
    line_content: str
    snapshot_name: str


class SnapshotSearchType(Enum):
    TEXT = "text"
    REGEX = "regex"


@dataclass
class SnapshotSearchParams:
    """
    Parametri per la ricerca all'interno di uno snapshot.
    """
    query: str
    search_type: SnapshotSearchType = SnapshotSearchType.TEXT
    extensions: list[str] = field(default_factory=list)


class SnapshotSearcher:
    """
    Cerca un contenuto testuale all'interno dei file di uno o più snapshot.
    """
    def __init__(self, catalogue: SnapshotCatalogue):
        """
        Inizializza lo SnapshotSearcher.

        Args:
            catalogue: Lo SnapshotCatalogue in cui cercare.
        """
        self.catalogue = catalogue

    def search(self, snapshot: Snapshot, params: SnapshotSearchParams, on_progress: Optional[SnapshotProgressCallback] = None) -> list[SnapshotSearchResult]:
        """
        Esegue una ricerca in un singolo snapshot in base ai parametri forniti.
        """
        snapshot_path = self.catalogue.get_snap_directory_path(snapshot)

        compiled_regex = None
        if params.search_type == SnapshotSearchType.REGEX:
            try:
                compiled_regex = re.compile(params.query)
            except re.error as e:
                logger.error(f"Invalid regex pattern provided: {e}")
                return []

        return self._search_in_snapshot_path(snapshot, snapshot_path, params, compiled_regex, on_progress)

    def search_list(self, snapshots: list[Snapshot], params: SnapshotSearchParams, on_progress: Optional[SnapshotProgressCallback] = None) -> list[SnapshotSearchResult]:
        """
        Esegue una ricerca in una lista di snapshot in base ai parametri forniti.
        """
        all_results: list[SnapshotSearchResult] = []
        for snapshot in snapshots:
            all_results.extend(self.search(snapshot, params, on_progress))
        return all_results

    def _search_in_snapshot_path(self, snapshot: Snapshot, snapshot_path: Path, params: SnapshotSearchParams, compiled_regex: Optional[re.Pattern], on_progress: Optional[SnapshotProgressCallback]) -> list[SnapshotSearchResult]:
        results: list[SnapshotSearchResult] = []
        if not snapshot_path or not snapshot_path.is_dir():
            logger.warning(f"Snapshot path '{snapshot_path}' for snapshot id '{snapshot.id}' does not exist or is not a directory.")
            return results

        # 1. Collect all files to be searched
        files_to_search: list[Path] = []
        for dir_assoc in snapshot.directories:
            copied_dir_path = snapshot_path.joinpath(dir_assoc.directory_name)
            if not copied_dir_path.is_dir():
                continue
            for file_path in copied_dir_path.rglob('*'):
                if self._should_search_file(file_path, params.extensions):
                    files_to_search.append(file_path)

        # 2. Iterate and report progress
        total_files = len(files_to_search)
        for i, file_path in enumerate(files_to_search):
            if on_progress:
                on_progress(file_path.name, total_files, i + 1)

            results.extend(self._search_in_file(file_path, params, compiled_regex, snapshot.name))

        return results


    def _should_search_file(self, file_path: Path, extensions: list[str]) -> bool:
        """Controlla se un file deve essere incluso nella ricerca."""
        if not file_path.is_file():
            return False
        if not extensions:
            return True  # Se non ci sono estensioni specificate, cerca in tutti i file
        return file_path.suffix in extensions

    def _search_in_file(self, file_path: Path, params: SnapshotSearchParams, compiled_regex: Optional[re.Pattern], snapshot_name: str) -> list[SnapshotSearchResult]:
        """Esegue la ricerca all'interno di un singolo file."""
        results: list[SnapshotSearchResult] = []
        try:
            with file_path.open('r', encoding='utf-8') as f:
                for i, line in enumerate(f, 1):
                    found = False
                    if params.search_type == SnapshotSearchType.TEXT:
                        if params.query in line:
                            found = True
                    elif compiled_regex and compiled_regex.search(line):
                        found = True

                    if found:
                        results.append(SnapshotSearchResult(
                            file_path=file_path,
                            searched_text=params.query,
                            line_number=i,
                            line_content=line.strip(),
                            snapshot_name=snapshot_name
                        ))
        except UnicodeDecodeError:
            logger.debug(f"Skipping binary file during search: {file_path}")
        except Exception as e:
            logger.warning(f"Error reading file {file_path} during search: {e}")
        return results