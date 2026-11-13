"""Public snapshot models, enums, edit payloads and settings.

Association and snapshot behavior is implemented in ``association_model`` and
``snapshot_model``. The public model declarations remain here to preserve their
historical import paths and class identities.
"""

import platform
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import ClassVar, Optional

from pylizlib.core.os.snap.association_model import _AssociationModel, validate_directory_component
from pylizlib.core.os.snap.copy_strategy import CopyMetadataMode, DirectoryCopyStrategy, ExtendedMetadataCopyStrategy, SequentialFileCopyStrategy
from pylizlib.core.os.snap.integrity import IntegrityManifest
from pylizlib.core.os.snap.snapshot_model import _SnapshotModel
from pylizlib.core.os.snap.storage.archive_limits import DEFAULT_MAX_ARCHIVE_ENTRIES, DEFAULT_MAX_ARCHIVE_UNCOMPRESSED_BYTES
from pylizlib.core.os.snap.storage.original_paths import normalize_original_path


@dataclass
class SnapDirAssociation(_AssociationModel):
    """Represents the association between an original directory and its copy within a snapshot.

    Attributes:
        index (int): Non-negative integer ordering label, independent of the new digest-based physical storage
            name.
        original_path (str): Rooted source spelling anchored on first initialization; link and parent components
            are not resolved, and Windows mapped drives use UNC.
        folder_id (str): Non-empty stable association identity; physical storage uses its digest, so it need not
            be a path component.
        mb_size (float | None): MiB content size (bytes / 1024**2), or None when unknown; a captured manifest is
            authoritative and construction does not scan sources.
        integrity_manifest (IntegrityManifest | None): Captured relative-path/type/size/SHA-256 mapping, or None
            for unverified legacy content.

    Notes:
        Construction anchors an initial relative source but does not recursively scan its size. Later validation
        rejects newly relative sources and can refresh a manifest-derived MiB size. New physical names depend on
        folder_id; serialized legacy storage_name values are retained by the loader and clone helper.
    """

    index: int
    original_path: str
    folder_id: str
    mb_size: float | None = None
    integrity_manifest: IntegrityManifest | None = None
    _current_index: ClassVar[int] = 0

    def validate(self) -> None:
        """Validate the fields that define this association's stored path.

        Returns:
            None: No return value.

        Raises:
            TypeError: An argument or mutable model field has a type rejected by this contract.
            ValueError: A value, path, resource limit or metadata field violates the validation rules described above.

        Notes:
            This mutates original_path normalization and may recalculate mb_size from integrity_manifest. Relative
            source paths are accepted only during initial construction. Validation does not recursively measure or
            copy the source tree.
        """
        return super().validate()

    @classmethod
    def next_index(cls):
        """Increments and returns the class-level index for new directory associations.

        Returns:
            int: The next integer index.
        """
        return super().next_index()

    @property
    def directory_name(self) -> str:
        """Return the persistent physical name for this association's stored copy.

        Returns:
            str: Persisted physical storage name when valid for the current folder_id, otherwise assoc- plus its
                SHA-256 digest. Access validates the model.

        Notes:
            Reading this property calls validate and can normalize the source or refresh its manifest-derived size.
            Persisted legacy storage names remain authoritative while their folder_id is unchanged.
        """
        return super().directory_name

    @staticmethod
    def gen_random(source_folder_for_choices: Path, folder_id_length: int = 4) -> "SnapDirAssociation":
        """Generates a single, random SnapDirAssociation for testing purposes.

        Args:
            source_folder_for_choices (Path): A directory from which a random subfolder will be chosen.
            folder_id_length (int): The length of the random `folder_id`.

        Returns:
            SnapDirAssociation: A new `SnapDirAssociation` instance with random data.
        """
        from pylizlib.core.os.snap.factories import gen_random_association

        return gen_random_association(source_folder_for_choices, folder_id_length)

    @staticmethod
    def gen_random_list(count: int, source_folder_for_choices: Path) -> list["SnapDirAssociation"]:
        """Generates a list of random SnapDirAssociation objects for testing.

        Args:
            count (int): The number of associations to generate.
            source_folder_for_choices (Path): The directory from which random subfolders will be chosen.

        Returns:
            list['SnapDirAssociation']: A list of new `SnapDirAssociation` instances.
        """
        from pylizlib.core.os.snap.factories import gen_random_association_list

        return gen_random_association_list(count, source_folder_for_choices)

    def copy_install_to(
        self,
        catalogue_target_path: Path,
        progress_callback=None,
        message_callback=None,
        *,
        copy_strategy: DirectoryCopyStrategy | None = None,
        manifest: IntegrityManifest | None = None,
        expected_manifest: IntegrityManifest | None = None,
    ):
        """Copy this association below a storage parent using its physical directory name.

        Args:
            catalogue_target_path (Path): Parent directory receiving this association's
                directory_name; this is not the association's final directory itself.
            progress_callback (CopyProgressCallback | None): Observer receiving copied and
                total byte counts; its return value does not cancel copying.
            message_callback (MessageCallback | None): Per-file status observer.
            copy_strategy (DirectoryCopyStrategy | None): Content/consistency policy, or the
                sequential default when omitted. Legacy delegates receive four positional
                arguments when neither manifest parameter is supplied.
            manifest (IntegrityManifest | None): Mutable captured-integrity output, updated
                only after successful copy by a conforming strategy.
            expected_manifest (IntegrityManifest | None): Captured content to verify before
                success; None permits copying without this expected-content comparison.

        Returns:
            None: The legacy facade deliberately discards the strategy's Path return value.
            If either manifest input/output is provided, captured content is recorded on this
            live association after destination checks complete.

        Raises:
            TypeError: If copy_strategy does not implement the public ABC.
            ValueError: If a root/child link, containment or post-copy entry check fails.
            OSError: If copying or filesystem inspection fails; partial-copy cleanup is attempted.
            SnapshotIntegrityError: If copied content disagrees with expected_manifest.

        Notes:
            Reading directory_name validates the mutable association. Current link checks are repeated around copying;
            this API is not an atomic multi-directory transaction.
        """
        return super().copy_install_to(catalogue_target_path, progress_callback, message_callback, copy_strategy=copy_strategy, manifest=manifest, expected_manifest=expected_manifest)


class SnapEditType(Enum):
    """Supported directory-association changes: add, remove or rename by identity."""

    ADD_DIR = "Add"
    REMOVE_DIR = "Remove"
    RENAME_DIR = "Rename"


class BackupType(Enum):
    """Select live associated directories or the complete stored snapshot tree."""

    ASSOCIATED_DIRECTORIES = 1
    SNAPSHOT_DIRECTORY = 2


@dataclass
class SnapshotBackupInfo:
    """Metadata read from a backup archive, with filename fallback for legacy ZIPs.

    Attributes:
        path (Path): Archive file path retained as supplied by the caller or directory listing.
        file_name (str): Archive basename, which can differ from authoritative embedded snapshot identity.
        snapshot_id (str | None): Embedded snapshot ID or legacy filename hint; None when identity cannot be
            recognized.
        backup_type (BackupType | None): Associated-directory or stored-snapshot archive type; None when not
            recognized.
        prefix (str): Prefix recorded in the manifest or inferred from the legacy filename; empty when unknown.
        created_at (datetime | None): Naive parsed backup timestamp, or None when unavailable; no timezone is
            inferred.
        is_export (bool): Whether manifest/filename identifies an export; unknown fallback entries use False.

    """

    path: Path
    file_name: str
    snapshot_id: str | None
    backup_type: BackupType | None
    prefix: str
    created_at: datetime | None
    is_export: bool


class SnapshotSortKey(Enum):
    """Snapshot attribute names accepted by the stable sorting helper."""

    ID = "id"
    NAME = "name"
    DESCRIPTION = "desc"
    AUTHOR = "author"
    DATE_CREATED = "date_created"
    DATE_MODIFIED = "date_modified"
    DATE_LAST_USED = "date_last_used"
    DATE_LAST_MODIFIED = "date_last_modified"
    ASSOC_DIR_MB_SIZE = "get_assoc_dir_mb_size"


@dataclass
class SnapEditAction:
    """Represents a single atomic change (addition, removal or rename of a directory)
    to a snapshot's structure.

    Attributes:
        action_type (SnapEditType): The type of edit (ADD_DIR, REMOVE_DIR or RENAME_DIR).
        timestamp (datetime): The time the action was created.
        new_path (str): The path of the directory being added (for ADD_DIR actions).
        folder_id_to_remove (str): The ID of the folder to remove (for REMOVE_DIR actions).
        directory_name_to_remove (str): The name of the directory to remove (for REMOVE_DIR actions).
        old_directory_name (str): Legacy stored source component for rename/removal identity resolution.
        new_directory_name (str): Legacy requested physical rename target component.
        folder_id (str): Non-empty stable association identity; physical storage uses its digest, so it need not
            be a path component.

    Notes:
        Construction validates field types and normalizes a non-empty ADD_DIR source. It does not establish that
        actions match stored metadata: the edit planner later resolves stable IDs and legacy names and rejects
        ambiguity.
    """

    action_type: SnapEditType
    timestamp: datetime = field(default_factory=datetime.now)
    new_path: str = ""
    folder_id_to_remove: str = ""
    directory_name_to_remove: str = ""
    old_directory_name: str = ""
    new_directory_name: str = ""
    folder_id: str = ""

    def __post_init__(self):
        """Validate a newly constructed edit before it can be used in a filesystem plan.

        Returns:
            None: No return value.
        """
        self._path_initialized = False
        self.validate()

    def validate(self) -> None:
        """Validate every action field before it can participate in a filesystem plan.

        Returns:
            None: No return value.

        Raises:
            TypeError: An argument or mutable model field has a type rejected by this contract.
        """
        if not isinstance(self.action_type, SnapEditType):
            raise TypeError("Snapshot edit action_type must be a SnapEditType.")
        if not isinstance(self.timestamp, datetime):
            raise TypeError("Snapshot edit timestamp must be a datetime.")
        for name in ("new_path", "folder_id_to_remove", "folder_id"):
            value = getattr(self, name)
            if not isinstance(value, str):
                raise TypeError(f"Snapshot edit {name} must be a string.")
        if self.action_type == SnapEditType.ADD_DIR and self.new_path:
            self.new_path = normalize_original_path(
                self.new_path,
                allow_relative=not self._path_initialized,
            )
        self._path_initialized = True
        for name in ("directory_name_to_remove", "old_directory_name", "new_directory_name"):
            validate_directory_component(getattr(self, name), name, allow_empty=True)


@dataclass
class SnapshotSettings:
    """Holds configuration settings for snapshot management.

    Attributes:
        json_filename (str): The name of the snapshot metadata file.
        backup_path (Path | None): The directory to store backups.
        backup_pre_install (bool): Whether to create a backup before installing a snapshot.
        backup_pre_modify (bool): Whether to create a backup before modifying a snapshot.
        backup_pre_delete (bool): Whether to create a backup before deleting a snapshot.
        install_with_everyone_full_control (bool): If on Windows, whether to grant 'Everyone' full control over
            installed directories (default False).
        snap_id_length (int): The character length for new snapshot IDs.
        folder_id_length (int): The character length for new folder association IDs.
        copy_strategy (DirectoryCopyStrategy): Live content-copy strategy; assigning it under EXTENDED mode adds
            one metadata wrapper when needed.
        allow_unverified_legacy_snapshots (bool): Permit installing legacy associations without an integrity
            manifest when True; False by default.
        copy_metadata_mode (CopyMetadataMode): BASIC or EXTENDED metadata selection; assigning it can wrap or
            unwrap copy_strategy.
        archive_temp_directory (Path | None): Optional ZIP extraction parent. None uses catalogue storage for
            SD/imports or a selected AD destination volume.
        max_archive_uncompressed_bytes (int | None): Maximum declared expanded ZIP bytes, default 100 * 1024**3;
            None disables the bound.
        max_archive_entries (int | None): Maximum ZIP members including directories/manifests, default 1000000;
            None disables the bound.

    Notes:
        This is mutable live configuration. Changing metadata mode can replace copy_strategy with a wrapper or its
        original delegate. Backup-before flags take effect only when backup_path is configured. Public
        manager/catalogue constructors retain their historical shared default settings objects unless a fresh
        settings instance is supplied.
    """

    json_filename: str = "snapshot.json"
    backup_path: Path | None = None
    backup_pre_install: bool = False
    backup_pre_modify: bool = False
    backup_pre_delete: bool = False
    install_with_everyone_full_control: bool = False
    snap_id_length: int = 20
    folder_id_length: int = 6
    copy_strategy: DirectoryCopyStrategy = field(default_factory=SequentialFileCopyStrategy)
    allow_unverified_legacy_snapshots: bool = False
    copy_metadata_mode: CopyMetadataMode = CopyMetadataMode.BASIC
    archive_temp_directory: Path | None = None
    max_archive_uncompressed_bytes: int | None = DEFAULT_MAX_ARCHIVE_UNCOMPRESSED_BYTES
    max_archive_entries: int | None = DEFAULT_MAX_ARCHIVE_ENTRIES

    def __setattr__(self, name, value):
        """Assign a setting while keeping copy strategy and metadata mode synchronized.

        Args:
            name (str): Setting attribute being assigned.
            value (object): New value, validated when assigning strategy or mode.

        Returns:
            None: The setting is assigned after any required strategy wrapping.

        Raises:
            TypeError: If copy_strategy or copy_metadata_mode has an invalid type.

        Notes:
            Switching away from EXTENDED unwraps its delegate. Assigning an explicit extended strategy while BASIC is
            already selected retains that strategy.
        """
        if name == "copy_strategy":
            value = self._copy_strategy_for_assignment(value)
        elif name == "copy_metadata_mode":
            self._update_strategy_for_mode(value)
        object.__setattr__(self, name, value)

    def _copy_strategy_for_assignment(self, value: object) -> DirectoryCopyStrategy:
        """Validate a strategy and add only the wrapper required by the current mode.

        Args:
            value (object): Strategy supplied during construction or later mutation.

        Returns:
            DirectoryCopyStrategy: The same strategy, or one extended-metadata wrapper around it. Already-extended
                strategies are never wrapped a second time.

        Raises:
            TypeError: If value does not implement the public strategy ABC.
        """
        if not isinstance(value, DirectoryCopyStrategy):
            raise TypeError("copy_strategy must implement DirectoryCopyStrategy.")
        mode = self.__dict__.get("copy_metadata_mode", CopyMetadataMode.BASIC)
        if mode is CopyMetadataMode.EXTENDED and not isinstance(value, ExtendedMetadataCopyStrategy):
            value = ExtendedMetadataCopyStrategy(value)
        return value

    def _update_strategy_for_mode(self, value: object) -> None:
        """Adjust the strategy before the new metadata mode itself is assigned.

        Args:
            value (object): Proposed CopyMetadataMode, validated before any mutation.

        Returns:
            None: The strategy is wrapped/unwrapped only for the existing mode rules; the caller remains responsible
                for assigning copy_metadata_mode afterward.

        Raises:
            TypeError: If value is not a CopyMetadataMode.
        """
        if not isinstance(value, CopyMetadataMode):
            raise TypeError("copy_metadata_mode must be a CopyMetadataMode.")
        previous_mode = self.__dict__.get("copy_metadata_mode")
        strategy = self.__dict__.get("copy_strategy")
        if value is CopyMetadataMode.EXTENDED and isinstance(strategy, DirectoryCopyStrategy) and not isinstance(strategy, ExtendedMetadataCopyStrategy):
            object.__setattr__(self, "copy_strategy", ExtendedMetadataCopyStrategy(strategy))
        elif previous_mode is CopyMetadataMode.EXTENDED and value is CopyMetadataMode.BASIC and isinstance(strategy, ExtendedMetadataCopyStrategy):
            object.__setattr__(self, "copy_strategy", strategy.delegate)

    def __post_init__(self):
        """Validate copy configuration and the legacy-install flag.

        Returns:
            None: No return value.

        Raises:
            TypeError: An argument or mutable model field has a type rejected by this contract.
            ValueError: A value, path, resource limit or metadata field violates the validation rules described above.

        Notes:
            The generated dataclass constructor already passes strategy/mode assignments through __setattr__.
            Construction and later mutations therefore use the same wrapper policy.
        """
        if not isinstance(self.copy_strategy, DirectoryCopyStrategy):
            raise TypeError("copy_strategy must implement DirectoryCopyStrategy.")
        if type(self.allow_unverified_legacy_snapshots) is not bool:
            raise TypeError("allow_unverified_legacy_snapshots must be a boolean.")
        if not isinstance(self.copy_metadata_mode, CopyMetadataMode):
            raise TypeError("copy_metadata_mode must be a CopyMetadataMode.")
        if self.archive_temp_directory is not None and not isinstance(self.archive_temp_directory, Path):
            raise TypeError("archive_temp_directory must be a pathlib.Path or None.")
        for name in ("max_archive_uncompressed_bytes", "max_archive_entries"):
            limit = getattr(self, name)
            if limit is not None and type(limit) is not int:
                raise TypeError(f"{name} must be a non-negative integer or None.")
            if limit is not None and limit < 0:
                raise ValueError(f"{name} cannot be negative.")

    @property
    def bck_before_install_enabled(self) -> bool:
        """Checks if backup before installation is enabled and a path is set.

        Returns:
            bool: True only when backup_pre_install is enabled and backup_path is configured.
        """
        return self.backup_pre_install and self.backup_path is not None

    @property
    def bck_before_modify_enabled(self) -> bool:
        """Checks if backup before modification is enabled and a path is set.

        Returns:
            bool: True only when backup_pre_modify is enabled and backup_path is configured.
        """
        return self.backup_pre_modify and self.backup_path is not None

    @property
    def bck_before_delete_enabled(self) -> bool:
        """Checks if backup before deletion is enabled and a path is set.

        Returns:
            bool: True only when backup_pre_delete is enabled and backup_path is configured.
        """
        return self.backup_pre_delete and self.backup_path is not None


@dataclass
class Snapshot(_SnapshotModel):
    """Represents a snapshot, which is a collection of directory associations
    and metadata at a specific point in time.

    Attributes:
        id (str): Non-empty snapshot ID used as one catalogue component under the library's existing component
            rules.
        name (str): Display name; it does not determine the stored directory component.
        desc (str): A description of the snapshot's purpose or contents.
        author (str): The user who created the snapshot.
        directories (list[SnapDirAssociation]): A list of `SnapDirAssociation` objects linking to the original
            directories.
        tags (list[str]): A list of strings for categorizing the snapshot.
        date_created (datetime): Creation datetime; the default is local naive datetime.now(), while supplied
            datetimes retain their timezone.
        date_modified (datetime | None): Last catalogue edit datetime or None; existing local/naive-compatible
            handling is retained.
        date_last_used (datetime | None): Last installed-use datetime or None; post-commit metadata errors expose
            whether its new value was published.
        date_last_modified (datetime | None): Last source synchronization datetime or None; library
            synchronization uses local datetime.now().
        os_created (str): Originating platform.system() label used to reject incompatible destructive operations.
        data (dict[str, str]): A dictionary for storing custom, arbitrary key-value data.
        capture_started_at (datetime | None): Timezone-aware acquisition start or None; library acquisitions use
            UTC.
        capture_completed_at (datetime | None): Timezone-aware acquisition completion or None; when both endpoints
            exist, completion cannot precede start.

    Notes:
        Construction validates contained associations and their path normalization. The model remains mutable and
        filesystem operations revalidate it. Association IDs and physical storage names must be unique; tags and
        custom data are strings. Capture endpoints must be timezone-aware, while other dates retain legacy
        datetime handling.
    """

    id: str
    name: str
    desc: str
    author: str = field(default="UnknownUser")
    directories: list[SnapDirAssociation] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    date_created: datetime = field(default_factory=datetime.now)
    date_modified: datetime | None = None
    date_last_used: datetime | None = None
    date_last_modified: datetime | None = None
    os_created: str = field(default_factory=platform.system)
    data: dict[str, str] = field(default_factory=dict)
    capture_started_at: datetime | None = None
    capture_completed_at: datetime | None = None

    def validate(self) -> None:
        """Validate snapshot metadata, including every association used for paths.

        Returns:
            None: No return value.

        Raises:
            TypeError: An argument or mutable model field has a type rejected by this contract.
            ValueError: A value, path, resource limit or metadata field violates the validation rules described above.
        """
        return super().validate()

    @property
    def tags_as_string(self) -> str:
        """Returns the list of tags as a single, comma-separated string.

        Returns:
            str: Sorted tags joined by comma-space, or one space when tags is empty.
        """
        return super().tags_as_string

    def get_for_table_array(self, key_list: list[str]) -> list[str]:
        """Generates a list of strings representing the snapshot's data for table display.

        Args:
            key_list (list[str]): A list of keys to retrieve from the snapshot's data dictionary.

        Returns:
            list[str]: Name, description, requested data values, date_created formatted as DD/MM/YYYY HH:MM:SS, and tags_as_string, in that order.
        """
        return super().get_for_table_array(key_list)

    @property
    def folder_name(self) -> str:
        """The name of the snapshot's folder in the catalogue, which is its ID.

        Returns:
            str: Snapshot ID used as its catalogue-directory component.
        """
        return super().folder_name

    @property
    def get_assoc_dir_mb_size(self) -> float:
        """Returns the sum of the mb_size of all associated directories.

        Returns:
            float: Sum of known captured association sizes in MiB; unknown values are omitted and an empty sum is
                zero.
        """
        return super().get_assoc_dir_mb_size

    def add_data_item(self, key: str, value: str) -> None:
        """Adds a key-value pair to the custom data dictionary.

        Args:
            key (str): The key for the data item.
            value (str): The value to store.

        Returns:
            None: No return value.
        """
        return super().add_data_item(key, value)

    def remove_data_item(self, key: str) -> Optional[str]:
        """Removes an item from the data dictionary and returns its value.

        Args:
            key (str): The key of the item to remove.

        Returns:
            Optional[str]: The value of the removed item, or None if the key was not found.
        """
        return super().remove_data_item(key)

    def has_data_item(self, key: str) -> bool:
        """Checks if a key exists in the data dictionary.

        Args:
            key (str): The key to check.

        Returns:
            bool: True if the key exists, False otherwise.
        """
        return super().has_data_item(key)

    def get_data_item(self, key: str, default: str = "") -> str:
        """Gets a value from the data dictionary, returning a default if the key is not found.

        Args:
            key (str): The key of the item to retrieve.
            default (str): The default value to return if the key is not found.

        Returns:
            str: The value associated with the key, or the default value.
        """
        return super().get_data_item(key, default)

    def clear_all_data(self) -> None:
        """Clears all items from the data dictionary.

        Returns:
            None: No return value.
        """
        return super().clear_all_data()

    def edit_data_item(self, key: str, new_value: str) -> None:
        """Edits the value of an existing item in the data dictionary.

        Args:
            key (str): The key of the item to edit.
            new_value (str): The new value to set.

        Returns:
            None: No return value.

        Raises:
            KeyError: If the key does not exist in the data dictionary.
        """
        return super().edit_data_item(key, new_value)

    def clone(self) -> "Snapshot":
        """Creates a deep, independent copy of the Snapshot instance.

        Returns:
            Snapshot: A new `Snapshot` object with the same data as the original.
        """
        return super().clone()
