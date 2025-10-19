import json
import os
import shutil
import zipfile
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import ClassVar, Optional

from pylizlib.core.data.gen import gen_random_string
from pylizlib.core.log.pylizLogger import logger
from pylizlib.core.os.path import random_subfolder, clear_folder_contents, clear_or_move_to_temp, duplicate_directory


# S = TypeVar("S")


# class CatalogueInterface(ABC, Generic[S]):
#
#     def __init__(self, path_catalogue: Path):
#         self.__setup_catalogue(path_catalogue)
#
#     def __setup_catalogue(self, path_catalogue: Path):
#         path_catalogue.mkdir(parents=True, exist_ok=True)
#         self.path_catalogue = path_catalogue
#
#     def update_catalogue_path(self, new_path: Path):
#         self.__setup_catalogue(new_path)
#
#     @abstractmethod
#     def add(self, data: S) -> S:
#         pass
#
#     @abstractmethod
#     def get_all(self) -> list[S]:
#         pass


@dataclass
class SnapDirAssociation:
    index: int
    original_path: str
    folder_id: str
    _current_index: ClassVar[int] = 0


    @classmethod
    def next_index(cls):
        cls._current_index += 1
        return cls._current_index

    @property
    def directory_name(self) -> str:
        return self.index.__str__() + "-" + Path(self.original_path).name


    @staticmethod
    def gen_random(source_folder_for_choices: Path):
        return SnapDirAssociation(
            index=SnapDirAssociation.next_index(),
            original_path=random_subfolder(source_folder_for_choices).__str__(),
            folder_id=gen_random_string(4)
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


@dataclass
class SnapEditAction:
    action_type: SnapEditType
    timestamp: datetime = datetime.now()
    new_path: str = ""
    folder_id_to_remove: str = ""



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
        return self.id + "-" + self.name

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












class SnapshotUtils:

    @staticmethod
    def gen_random_snap(source_folder_for_choices: Path, id_length: int = 10, ) -> Snapshot:
        dirs = SnapDirAssociation.gen_random_list(3, source_folder_for_choices)
        return Snapshot(
            id=gen_random_string(id_length),
            name="Snapshot " + gen_random_string(5),
            desc="Randomly generated snapshot",
            author="User",
            directories=dirs,
            tags=["example", "test"]
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
            folder_id = old_path_to_assoc[path].folder_id
            edits.append(SnapEditAction(
                action_type=SnapEditType.REMOVE_DIR,
                folder_id_to_remove=folder_id
            ))

        return edits




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
            json_filename: str = "snapshot.json"
    ):
        self.snapshot = snapshot
        self.json_filename = json_filename
        self.path_catalogue = catalogue_path
        self.path_snapshot = SnapshotUtils.get_snapshot_path(self.snapshot.folder_name, self.path_catalogue)
        self.path_snapshot_json = SnapshotUtils.get_snapshot_json_path(self.snapshot.folder_name, self.path_catalogue, self.json_filename)

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
            folder_id=gen_random_string(4)
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
        for edit in edits:
            if edit.action_type == SnapEditType.ADD_DIR:
                self.install_directory(Path(edit.new_path))
            elif edit.action_type == SnapEditType.REMOVE_DIR:
                self.uninstall_directory_by_folder_id(edit.folder_id_to_remove)

    def duplicate(self):
        if not self.path_snapshot.exists():
            raise FileNotFoundError(f"The snapshot path {self.path_snapshot} does not exist.")
        new_snap = self.snapshot
        new_snap.id = gen_random_string(10)
        new_snap.name = self.snapshot.name + " Copy"
        new_snap.date_created = datetime.now()
        new_snap_path = SnapshotUtils.get_snapshot_path(new_snap.folder_name, self.path_catalogue)
        new_snap_json_path = SnapshotUtils.get_snapshot_json_path(new_snap.folder_name, self.path_catalogue, self.json_filename)
        duplicate_directory(self.path_snapshot, new_snap_path, "")
        SnapshotSerializer.to_json(new_snap, new_snap_json_path)

    def install(self):
        for dir_assoc in self.snapshot.directories:
            dir_assoc.copy_install_to(Path(dir_assoc.original_path))
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
            snapshot_json_filename: str = "snapshot.json",
            backup_path: Path | None = None,
            backup_pre_install: bool = False,
            backup_pre_modify: bool = False,
            backup_pre_delete: bool = False,
    ):
        self.path_catalogue = path_catalogue
        self.snapshot_json_filename = snapshot_json_filename
        self.backup_path = backup_path
        self.backup_pre_install = backup_pre_install
        self.backup_pre_modify = backup_pre_modify
        self.backup_pre_delete = backup_pre_delete

        self.backup_pre_install_enabled = backup_pre_install and backup_path is not None
        self.backup_pre_modify_enabled = backup_pre_modify and backup_path is not None
        self.backup_pre_delete_enabled = backup_pre_delete and backup_path is not None

        self.path_catalogue.mkdir(parents=True, exist_ok=True)


    def add(self, snap: Snapshot):
        snap_manager = SnapshotManager(snap, self.path_catalogue, self.snapshot_json_filename)
        snap_manager.create()

    def delete(self, snap: Snapshot):
        snap_manager = SnapshotManager(snap, self.path_catalogue, self.snapshot_json_filename)
        if self.backup_pre_delete_enabled:
            snap_manager.backup_snap_directory(self.backup_path)
        snap_manager.delete()

    def get_all(self) -> list[Snapshot]:
        self.path_catalogue.mkdir(parents=True, exist_ok=True)
        snapshots: list[Snapshot] = []
        for current_dir in self.path_catalogue.iterdir():
            if current_dir.is_dir():
                snap = SnapshotUtils.get_snapshot_from_path(current_dir, self.snapshot_json_filename)
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
        snap_manager = SnapshotManager(snap, self.path_catalogue, self.snapshot_json_filename)
        if self.backup_pre_modify_enabled:
            snap_manager.backup_snap_directory(self.backup_path)
        snap_manager.update_json_base_fields()
        snap_manager.update_json_data_fields()
        snap_manager.update_from_actions_list(edits)

    def duplicate_by_id(self, snap_id: str):
        snap = self.get_by_id(snap_id)
        if snap is None:
            raise ValueError(f"No snapshot found with ID {snap_id}")
        snap_manager = SnapshotManager(snap, self.path_catalogue, self.snapshot_json_filename)
        snap_manager.duplicate()

    def install(self, snap: Snapshot):
        snap_manager = SnapshotManager(snap, self.path_catalogue, self.snapshot_json_filename)
        if self.backup_pre_install_enabled:
            snap_manager.backup_associated("preinstall", self.backup_path)
        snap_manager.install()

    def exists(self, snap_id: str) -> bool:
        return self.get_by_id(snap_id) is not None

    def get_snap_directory_path(self, snap: Snapshot) -> Path | None:
        if not self.exists(snap.id):
            return None
        return SnapshotUtils.get_snapshot_path(snap.folder_name, self.path_catalogue)




