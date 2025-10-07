import json
import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import ClassVar, Any, TypeVar, Protocol, Generic, Optional

from pylizlib.core.data.gen import gen_random_string
from pylizlib.core.os.path import random_subfolder, clear_folder_contents, clear_or_move_to_temp

S = TypeVar("S")


class CatalogueInterface(ABC, Generic[S]):

    def __init__(self, path_catalogue: Path):
        self.__setup_catalogue(path_catalogue)

    def __setup_catalogue(self, path_catalogue: Path):
        path_catalogue.mkdir(parents=True, exist_ok=True)
        self.path_catalogue = path_catalogue

    def update_catalogue_path(self, new_path: Path):
        self.__setup_catalogue(new_path)

    @abstractmethod
    def add(self, data: S) -> S:
        pass

    @abstractmethod
    def get_all(self) -> list[S]:
        pass


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
    UPDATE_DATA = "Update"


@dataclass
class SnapEditAction:
    action_type: SnapEditType
    timestamp: datetime = datetime.now()
    new_data: str = ""


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
    def folder_name(self) -> str:
        return self.id + "-" + self.name

    @classmethod
    def get_json_name(cls):
        return "snapshot.json"


    def add_data_item(self, key: str, value: str) -> None:
        """Aggiunge un elemento al dizionario."""
        self.data[key] = value

    def remove_data_item(self, key: str) -> Optional[str]:
        """Rimuove un elemento dal dizionario e restituisce il valore rimosso."""
        return self.data.pop(key, None)

    def has_data_item(self, key: str) -> bool:
        """Verifica se una chiave esiste nel dizionario."""
        return key in self.data

    def get_data_tem(self, key: str, default: str = "") -> str:
        """Ottiene un valore dal dizionario con un default."""
        return self.data.get(key, default)

    def clear_all_data(self) -> None:
        """Pulisce tutti gli elementi del dizionario."""
        self.data.clear()



    @staticmethod
    def gen_random(source_folder_for_choices: Path, id_length: int = 10, ) -> 'Snapshot':
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
    def get_snapshot_from_path(path_snapshot: Path) -> 'Snapshot | None':
        if path_snapshot.is_file():
            raise ValueError(f"The provided path {path_snapshot} is not a directory.")
        if not path_snapshot.exists():
            raise FileNotFoundError(f"The provided path {path_snapshot} does not exist.")
        path_snapshot_json = path_snapshot.joinpath(Snapshot.get_json_name())
        if not path_snapshot_json.is_file():
            raise FileNotFoundError(f"No snapshot.json file found in {path_snapshot}.")
        return SnapshotSerializer.from_json(path_snapshot_json)


    def __get_snap_path(self, path_catalogue: Path):
        path_snapshot = path_catalogue.joinpath(self.folder_name)
        path_snapshot.mkdir(parents=True, exist_ok=True)
        return path_snapshot

    def __get_snap_json_path(self, path_catalogue: Path):
        return self.__get_snap_path(path_catalogue).joinpath(self.get_json_name())

    def save_json(self, path_catalogue: Path):
        path_snapshot_json = self.__get_snap_json_path(path_catalogue)
        SnapshotSerializer.to_json(self, path_snapshot_json)

    def __update_json_data_fields(self, path_catalogue: Path):
        path_snapshot_json = self.__get_snap_json_path(path_catalogue)
        SnapshotSerializer.update_field(path_snapshot_json, "data", self.data)
        SnapshotSerializer.update_field(path_snapshot_json, "date_last_modified", datetime.now().isoformat())
        self.date_last_modified = datetime.now()

    def __update_json_base_fields(self, path_catalogue: Path):
        path_snapshot_json = self.__get_snap_json_path(path_catalogue)
        SnapshotSerializer.update_field(path_snapshot_json, "name", self.name)
        SnapshotSerializer.update_field(path_snapshot_json, "desc", self.desc)
        SnapshotSerializer.update_field(path_snapshot_json, "author", self.author)
        SnapshotSerializer.update_field(path_snapshot_json, "tags", self.tags)
        SnapshotSerializer.update_field(path_snapshot_json, "date_modified", datetime.now().isoformat())
        self.date_modified = datetime.now()

    def clear_snapshot(self, path_catalogue: Path):
        path_snapshot = self.__get_snap_path(path_catalogue)
        clear_or_move_to_temp(path_snapshot)

    def update(self, path_catalogue: Path):
        path_snapshot = self.__get_snap_path(path_catalogue)
        if not path_snapshot.exists():
            raise FileNotFoundError(f"The snapshot directory {path_snapshot} does not exist.")
        self.__update_json_base_fields(path_catalogue)
        self.__update_json_data_fields(path_catalogue)


    def create(self, path_catalogue: Path):
        path_snapshot = self.__get_snap_path(path_catalogue)
        for snap_dir in self.directories:
            snap_dir.copy_install_to(path_snapshot)
        self.save_json(path_catalogue)




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



class SnapshotCatalogue(CatalogueInterface[Snapshot]):

    def __init__(self, path_catalogue: Path):
        super().__init__(path_catalogue)

    def add(self, data: S) -> S:
        snapshot: Snapshot = data
        snapshot.create(self.path_catalogue)

    def get_all(self) -> list[S]:
        snapshots: list[Snapshot] = []
        for current_dir in self.path_catalogue.iterdir():
            if current_dir.is_dir():
                snap = Snapshot.get_snapshot_from_path(current_dir)
                if snap is not None:
                    snapshots.append(snap)
        return snapshots

    def remove(self, snapshot: Snapshot) -> None:
        snapshot.clear_snapshot(self.path_catalogue)

    def update(self, snapshot: Snapshot) -> None:
        snapshot.update(self.path_catalogue)


    #
    # @staticmethod
    # def duplicate(path_catalogue: Path, snapshot: Snapshot) -> Snapshot:
    #     path_catalogue.mkdir(parents=True, exist_ok=True)
    #     pass
    #
    # @staticmethod
    # def get_all(path_catalogue: Path) -> list[Snapshot]:
    #     path_catalogue.mkdir(parents=True, exist_ok=True)
    #     snapshots: list[Snapshot] = []
    #     for current_dir in path_catalogue.iterdir():
    #         if current_dir.is_dir():
    #             snap = Snapshot.get_snapshot_from_path(current_dir)
    #             if snap is not None:
    #                 snapshots.append(snap)
    #     return snapshots
    #
    # @staticmethod
    # def install_attached_dirs(path_catalogue: Path, snapshot: Snapshot) -> None:
    #     pass
