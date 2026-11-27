"""Collect snapshot backup members and publish verified archives exclusively."""

import hashlib
import json
import stat
import tempfile
import zipfile
from collections.abc import Callable
from datetime import datetime
from functools import partial
from pathlib import Path

from pylizlib.core.log.pylizLogger import logger
from pylizlib.core.os.archives.zip.publication import write_verified_zip_exclusive as _write_verified_zip_exclusive
from pylizlib.core.os.filesystem.tree import is_link_or_junction
from pylizlib.core.os.paths.safety import assert_no_link_components
from pylizlib.core.os.snap.copy_strategy import SourceChangedError
from pylizlib.core.os.snap.domain import BackupType, SnapDirAssociation, Snapshot
from pylizlib.core.os.snap.integrity import IntegrityManifest, assert_manifest_matches
from pylizlib.core.os.snap.operations.archives import SnapshotIncompleteError
from pylizlib.core.os.snap.operations.backup.associations import association_identities
from pylizlib.core.os.snap.operations.backup_manifest import BACKUP_MANIFEST_NAME, build_backup_manifest, parse_backup_manifest
from pylizlib.core.os.snap.operations.backup_names import build_backup_filename
from pylizlib.core.os.snap.storage.archives import validate_zip_archive
from pylizlib.core.os.snap.storage.context import SnapshotStorage
from pylizlib.core.os.snap.storage.coordination import coordinated
from pylizlib.core.os.snap.storage.metadata import SnapshotJsonCodec
from pylizlib.core.os.snap.storage.paths import assert_no_operational_storage
from pylizlib.core.os.snap.storage.transactions import recover_storage_transactions
from pylizlib.core.os.snap.storage.tree import assert_no_symlinks, iter_tree_entries_strict


def verify_displaced_sources(archive_path: Path | None, displaced: dict[str, Path], *, merge: bool = False, subject: str = "Install destination") -> None:
    """Compare displaced directories or merge entries with their restorable ZIP members.

    Args:
        archive_path (Path | None): Published backup, omitted only when no destinations existed.
        displaced (dict[str, Path]): Archived root names mapped to the journal's saved copies.
        merge (bool): In merge mode, each root name includes the replaced top-level child.
        subject (str): Name of the affected directory in discrepancy messages.

    Returns:
        None: Every displaced file and directory is backed up.

    Raises:
        SourceChangedError: The displaced entries differ from the completed archive.
        OSError: The archive or a displaced entry cannot be verified.
    """
    if not displaced:
        return
    if archive_path is None:
        raise SourceChangedError("Install destinations appeared after the pre-install backup was prepared.")

    paths = dict(displaced)
    for member_root, source_root in displaced.items():
        assert_no_link_components(source_root)
        if source_root.is_dir():
            for entry in iter_tree_entries_strict(source_root):
                paths[f"{member_root}/{entry.relative_to(source_root).as_posix()}"] = entry

    depth = 2 if merge else 1
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            name = member.filename.rstrip("/")
            root = "/".join(name.split("/", depth)[:depth])
            if root not in displaced:
                continue
            source = paths.pop(name, None)
            if source is None or source.is_dir() != member.is_dir():
                raise SourceChangedError(f"{subject} changed after backup: '{name}'.")
            if member.is_dir():
                continue
            info = source.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_size != member.file_size:
                raise SourceChangedError(f"{subject} changed after backup: '{name}'.")
            with source.open("rb") as current_file, archive.open(member) as backed_up_file:
                if hashlib.file_digest(current_file, "sha256").digest() != hashlib.file_digest(backed_up_file, "sha256").digest():
                    raise SourceChangedError(f"{subject} changed after backup: '{name}'.")
    if paths:
        raise SourceChangedError(f"{subject} changed after backup: '{next(iter(paths))}'.")


class BackupCreator:
    """Build and verify ZIP backups of one stored snapshot or its live copies.

    Attributes:
        storage (SnapshotStorage): Live snapshot model, settings, captured layout and protected metadata adapter
            for this operation.
        now (Callable[[], datetime]): Zero-argument clock called once per backup to produce the existing
            filename/manifest timestamp.
    """

    def __init__(self, storage: SnapshotStorage, *, now: Callable[[], datetime] = datetime.now):
        """Bind the snapshot state and clock without reading or copying content.

        Args:
            storage (SnapshotStorage): Live model, layout, copy strategy and serializer.
            now (Callable[[], datetime]): Clock called once for each backup timestamp.

        Returns:
            None: The creator retains both dependencies by reference.
        """
        self.storage = storage
        self.now = now

    @coordinated("storage.path_catalogue")
    def create_backup(self, backup_path: Path, prefix: str, backup_type: "BackupType", is_export: bool = False, message_callback=None) -> Path:
        """Creates, verifies and atomically publishes a zip archive of the snapshot's data.
        Failures propagate to the caller so protected operations cannot continue.

        Args:
            backup_path (Path): The directory where the backup zip file will be saved.
            prefix (str): A prefix for the backup filename.
            backup_type (BackupType): The type of backup to create (associated directories or the snapshot directory).
            is_export (bool): If True, the filename will be formatted as an export.
            message_callback (MessageCallback | None): Optional status observer receiving one message string; its
                exceptions propagate according to the calling operation.

        Returns:
            Path: The path of the verified, published archive.

        Raises:
            SnapshotBusyError: Another operation owns the catalogue, or an observer attempts a modifying call.
            SnapshotIncompleteError: If any associated source folder is missing or ceases to be readable as a
                directory during enumeration.
            ValueError: A value, path, resource limit or metadata field violates the validation rules described above.
            FileNotFoundError: A required source, stored association or metadata entry is absent.
        """
        result = self._create_backup(backup_path, prefix, backup_type, is_export, message_callback)
        assert result is not None
        return result

    @coordinated("storage.path_catalogue")
    def create_backup_for_existing_associations(self, backup_path: Path, prefix: str, message_callback=None) -> Path | None:
        """Back up real association destinations that currently exist, skipping absent destinations.

        Args:
            backup_path (Path): Directory receiving the completed archive.
            prefix (str): Prefix for the backup filename.
            message_callback (MessageCallback | None): Optional status observer receiving one message string; its
                exceptions propagate according to the calling operation.

        Returns:
            Path | None: Published archive, or None when no association destination exists to protect.

        Raises:
            SnapshotBusyError: Another operation owns the catalogue, or an observer attempts a modifying call.
            SnapshotIncompleteError: An existing association root is not readable as a directory.
            ValueError: A value, path, resource limit or metadata field violates the validation rules described above.
        """
        return self._create_backup(backup_path, prefix, BackupType.ASSOCIATED_DIRECTORIES, False, message_callback, only_existing=True)

    @coordinated("storage.path_catalogue")
    def create_backup_for_associations(
        self,
        backup_path: Path,
        prefix: str,
        associations: list[SnapDirAssociation],
        message_callback=None,
    ) -> Path:
        """Back up a caller-selected set of local roots without weakening complete AD backups.

        Args:
            backup_path (Path): Directory receiving the completed archive.
            prefix (str): Prefix for the backup filename.
            associations (list[SnapDirAssociation]): Exact roots to archive and record in the manifest.
            message_callback (MessageCallback | None): Optional status observer receiving one message string; its
                exceptions propagate according to the calling operation.

        Returns:
            Path: Published archive path after exclusive publication.

        Raises:
            SnapshotIncompleteError: A selected source root is missing or unreadable.
            ValueError: A selected source is unsafe or archive publication violates path policy.
        """
        result = self._create_backup(backup_path, prefix, BackupType.ASSOCIATED_DIRECTORIES, False, message_callback, association_subset=associations)
        assert result is not None
        return result

    @coordinated("storage.path_catalogue")
    def export_captured_associations(self, destination: Path, message_callback=None) -> Path:
        """Publish an AD export sourced from the stored association trees.

        Args:
            destination (Path): Folder receiving the completed export.
            message_callback (MessageCallback | None): Optional per-entry status observer.

        Returns:
            Path: Published archive path.
        """
        result = self._create_backup(destination, "export", BackupType.ASSOCIATED_DIRECTORIES, True, message_callback, captured=True)
        assert result is not None
        return result

    def _create_backup(
        self,
        backup_path: Path,
        prefix: str,
        backup_type: BackupType,
        is_export: bool,
        message_callback,
        *,
        only_existing: bool = False,
        association_subset: list[SnapDirAssociation] | None = None,
        captured: bool = False,
    ) -> Path | None:
        """Create and publish an archive, optionally selecting a subset of AD roots.

        Args:
            backup_path (Path): Directory receiving the completed archive and temporary manifest.
            prefix (str): Prefix included in the generated archive filename and manifest.
            backup_type (BackupType): Whether to archive associated directories or the stored snapshot directory.
            is_export (bool): Whether the archive uses the export naming convention.
            message_callback (MessageCallback | None): Optional per-entry status observer.
            only_existing (bool): Skip absent association destinations and return None when none exist.
            association_subset (list[SnapDirAssociation] | None): Exact AD roots to archive, or None to use the
                snapshot's associations.
            captured (bool): Read AD content from stored copies instead of original paths.

        Returns:
            Path | None: Published verified archive, or None when an only-existing backup has no targets.

        Raises:
            SnapshotIncompleteError: A selected association cannot be completely archived.
            OSError: Archive creation or publication fails.
            ValueError: A path, archive entry or metadata field violates backup validation.
        """
        try:
            if backup_type not in (BackupType.ASSOCIATED_DIRECTORIES, BackupType.SNAPSHOT_DIRECTORY):
                raise ValueError(f"Unsupported backup type: {backup_type}")
            recover_storage_transactions(self.storage)
            self.storage.snapshot.validate()
            self.storage.root_path()
            snapshot_json_path = self.storage.child_path(self.storage.settings.json_filename)
            manifest_snapshot = self.storage.snapshot

            # Edits may already hold the proposed model while disk still holds the old snapshot.
            if backup_type == BackupType.SNAPSHOT_DIRECTORY:
                manifest_snapshot = self.storage.metadata.from_json(snapshot_json_path)
                if manifest_snapshot.id != self.storage.snapshot.id:
                    raise ValueError("Stored snapshot ID does not match the requested backup.")
            timestamp = self.now().strftime("%Y%m%d_%H%M%S")

            associations = self.storage.snapshot.directories if backup_type == BackupType.ASSOCIATED_DIRECTORIES else None
            if association_subset is not None:
                associations = association_subset
            elif only_existing:
                associations = [association for association in self.storage.snapshot.directories if self._association_target_exists(association)]
                if not associations:
                    logger.info("Skipped pre-install backup snapshot=%s because no associated destination exists", self.storage.snapshot.id)
                    return None
                if len(associations) < len(self.storage.snapshot.directories):
                    logger.info(
                        "Pre-install backup will cover %s of %s associated destinations snapshot=%s",
                        len(associations),
                        len(self.storage.snapshot.directories),
                        self.storage.snapshot.id,
                    )

            base_zip_name = build_backup_filename(self.storage.snapshot.id, prefix, backup_type, timestamp, is_export)
            archived_roots = (
                [self._association_source(association, captured=captured) for association in (associations or [])] if backup_type == BackupType.ASSOCIATED_DIRECTORIES else [self.storage.root_path()]
            )
            self._validate_archive_destination(backup_path / base_zip_name, archived_roots)

            backup_path.mkdir(parents=True, exist_ok=True)

            entries = list(self._files_to_archive(backup_type, associations=associations, captured=captured))
            if any(archive_name == Path(BACKUP_MANIFEST_NAME) for _, archive_name in entries):
                raise ValueError(f"Snapshot content conflicts with reserved backup manifest '{BACKUP_MANIFEST_NAME}'.")
            manifest_path = self._write_backup_manifest(backup_path, manifest_snapshot, backup_type, prefix, is_export, timestamp, associations=associations)
            entries.append((manifest_path, Path(BACKUP_MANIFEST_NAME)))
            try:
                result = self._publish_unique_archive(backup_path, base_zip_name, entries, backup_type, message_callback)
                logger.info("Created snapshot backup snapshot=%s archive=%s type=%s", self.storage.snapshot.id, result, backup_type.name)
                return result
            finally:
                if manifest_path is not None:
                    try:
                        manifest_path.unlink(missing_ok=True)
                    except OSError as error:
                        logger.warning(f"Could not remove temporary associated-directories manifest '{manifest_path}': {error}")
        except Exception as e:
            logger.error(f"Failed to create backup for snapshot '{self.storage.snapshot.id}': {e}")
            raise

    @staticmethod
    def _association_target_exists(association: SnapDirAssociation) -> bool:
        """Check path-entry presence without following a dangling symbolic link.

        Args:
            association (SnapDirAssociation): Association whose original destination is checked.

        Returns:
            bool: True only when the destination is a real directory; absent entries, files and links are excluded.
        """
        try:
            path = Path(association.original_path)
            mode = path.lstat().st_mode
        except FileNotFoundError:
            return False
        if is_link_or_junction(path) or not stat.S_ISDIR(mode):
            return False
        assert_no_link_components(path)
        return True

    @staticmethod
    def _validate_archive_destination(destination: Path, archived_roots: list[Path]) -> None:
        """Reject a ZIP destination inside any tree that the archive enumerates.

        Args:
            destination (Path): Target path receiving the copied content or metadata.
            archived_roots (list[Path]): All source tree roots used to reject a backup destination nested inside
                archived content.

        Returns:
            None: No return value.

        Raises:
            ValueError: A value, path, resource limit or metadata field violates the validation rules described above.
        """
        try:
            resolved_destination = destination.resolve(strict=False)
            resolved_roots = [(root, root.resolve(strict=False)) for root in archived_roots]
        except Exception as error:
            raise ValueError(f"Cannot verify backup destination '{destination}': {error}") from error

        for source_root, resolved_root in resolved_roots:
            if resolved_destination.is_relative_to(resolved_root):
                raise ValueError(f"Backup destination '{destination}' is inside archived source '{source_root}'.")

    def _write_backup_manifest(
        self,
        directory: Path,
        snapshot: Snapshot,
        backup_type: BackupType,
        prefix: str,
        is_export: bool,
        timestamp: str,
        *,
        associations: list[SnapDirAssociation] | None = None,
    ) -> Path:
        """Write a temporary typed manifest with identity and associations for either backup type.

        Args:
            directory (Path): Existing directory receiving the temporary manifest file.
            snapshot (Snapshot): Metadata describing the snapshot version included in the archive.
            backup_type (BackupType): Whether to archive live associated directories (AD) or the stored snapshot tree
                (SD).
            prefix (str): Backup filename prefix recorded unchanged in the archive manifest.
            is_export (bool): Whether the backup uses the existing export naming convention.
            timestamp (str): Creation timestamp in YYYYMMDD_HHMMSS format using the existing naive/local naming
                convention.
            associations (list[SnapDirAssociation] | None): AD subset represented by the archive, or None to record
                every snapshot association.

        Returns:
            Path: Temporary UTF-8 JSON manifest path; the caller owns unlinking it after archive publication.
        """
        data = build_backup_manifest(snapshot, backup_type, prefix, is_export, timestamp, association_subset=associations)
        temporary_path = None
        try:
            temporary_file_context = tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=directory,
                prefix=".backup_metadata_",
                suffix=".partial",
                delete=False,
            )
            with temporary_file_context as temporary_file:
                temporary_path = Path(temporary_file.name)
                json.dump(data, temporary_file, ensure_ascii=False, indent=2)
            return temporary_path
        except Exception:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError as error:
                    logger.warning(f"Could not remove unfinished backup manifest '{temporary_path}': {error}")
            raise

    def _association_source(self, association: SnapDirAssociation, *, captured: bool) -> Path:
        """Resolve the source tree selected for an AD archive.

        Args:
            association (SnapDirAssociation): Association supplying both source locations.
            captured (bool): Select the copy stored in the catalogue.

        Returns:
            Path: Root of the original or captured association tree.
        """
        return self.storage.child_path(association.directory_name) if captured else Path(association.original_path)

    def _files_to_archive(self, backup_type: BackupType, *, associations: list[SnapDirAssociation] | None = None, captured: bool = False):
        """Enumerate stored or live files using their distinct existing link policies.

        Args:
            backup_type (BackupType): Whether to archive live associated directories (AD) or the stored snapshot tree
                (SD).
            associations (list[SnapDirAssociation] | None): Optional AD subset to enumerate; None selects every
                association in the snapshot.
            captured (bool): Read AD content from the stored association trees.

        Yields:
            tuple[Path, Path]: Source entry and relative archive name, including empty directories.

        Raises:
            SnapshotIncompleteError: Required association directories are missing or unexpected archive roots are
                present; inspect the exception lists.
        """
        if backup_type == BackupType.ASSOCIATED_DIRECTORIES:
            sources = []
            missing_folders = []
            source_associations = self.storage.snapshot.directories if associations is None else associations
            for association in source_associations:
                folder = self._association_source(association, captured=captured)
                try:
                    mode = folder.stat().st_mode
                except (FileNotFoundError, NotADirectoryError):
                    missing_folders.append(association.original_path)
                    continue
                if not stat.S_ISDIR(mode):
                    missing_folders.append(association.original_path)
                    continue
                sources.append((association, folder))

            if missing_folders:
                raise SnapshotIncompleteError("Associated-directory backup", missing_folders)

            # Enumerate every source before yielding any member to the ZIP writer.
            entries = []
            for association, folder in sources:
                entries.append((folder, Path(association.directory_name)))
                try:
                    for tree_entry in iter_tree_entries_strict(folder):
                        entries.append((tree_entry, Path(association.directory_name) / tree_entry.relative_to(folder)))
                except (FileNotFoundError, NotADirectoryError):
                    missing_folders.append(association.original_path)

            if missing_folders:
                raise SnapshotIncompleteError("Associated-directory backup", missing_folders)

            yield from entries
        else:
            snapshot_root = self.storage.root_path()
            assert_no_symlinks(snapshot_root)
            assert_no_operational_storage(snapshot_root)
            for tree_entry in iter_tree_entries_strict(snapshot_root):
                yield tree_entry, tree_entry.relative_to(self.storage.path_snapshot)

    def _validate_written_archive(self, archive: Path, *, backup_type: BackupType) -> None:
        """Apply the restore member and resource checks before publication.

        Args:
            archive (Path): Completed ZIP in private staging.
            backup_type (BackupType): SD archives also verify captured content against their metadata.

        Returns:
            None: The archive passed restore preflight.
        """
        validate_zip_archive(
            archive,
            max_entries=self.storage.settings.max_archive_entries,
            max_uncompressed_bytes=self.storage.settings.max_archive_uncompressed_bytes,
        )
        if backup_type == BackupType.SNAPSHOT_DIRECTORY:
            self._validate_snapshot_archive(archive)

    def _validate_snapshot_archive(self, archive_path: Path) -> None:
        """Check archived SD contents against the same metadata used by restore.

        Args:
            archive_path (Path): Closed private ZIP that passed member validation.

        Returns:
            None: All association roots and available integrity manifests agree with the archived bytes.

        Raises:
            FileNotFoundError: An association directory is missing from the archive.
            SnapshotIntegrityError: Archived content differs from a captured manifest.
            ValueError: Snapshot identity or association metadata does not agree across archive members.
        """
        with zipfile.ZipFile(archive_path) as archive:
            snapshot = SnapshotJsonCodec.decode(archive.read(self.storage.settings.json_filename).decode("utf-8"))
            manifest = parse_backup_manifest(json.loads(archive.read(BACKUP_MANIFEST_NAME)))
            if snapshot.id != manifest.snapshot_id or association_identities(snapshot.directories) != association_identities(manifest.associations):
                raise ValueError("Snapshot-directory metadata does not match the backup manifest.")

            names = set(archive.namelist())
            observed: dict[str, IntegrityManifest] = {}
            for association in snapshot.directories:
                root = association.directory_name
                if f"{root}/" not in names:
                    raise FileNotFoundError(f"Snapshot backup is missing association directory '{root}'.")
                if association.integrity_manifest is not None:
                    observed[root] = {".": {"type": "directory", "size": 0, "sha256": None}}

            for member in archive.infolist():
                root, _, relative_path = member.filename.rstrip("/").partition("/")
                if root not in observed or not relative_path:
                    continue
                if member.is_dir():
                    observed[root][relative_path] = {"type": "directory", "size": 0, "sha256": None}
                else:
                    with archive.open(member) as stream:
                        digest = hashlib.file_digest(stream, "sha256").hexdigest()
                    observed[root][relative_path] = {"type": "file", "size": member.file_size, "sha256": digest}

            for association in snapshot.directories:
                if association.integrity_manifest is not None:
                    assert_manifest_matches(association.integrity_manifest, observed[association.directory_name])

    def _publish_unique_archive(self, backup_path: Path, base_zip_name: str, entries: list[tuple[Path, Path]], backup_type: BackupType, message_callback=None) -> Path:
        """Retry only final-name collisions while retaining exclusive publication.

        Args:
            backup_path (Path): Existing directory receiving the verified archive.
            base_zip_name (str): Initial filename, including the .zip suffix.
            entries (list[tuple[Path, Path]]): Fully enumerated sources and member names.
            backup_type (BackupType): Archive type used to select post-write checks.
            message_callback (Callable[[str], None] | None): Per-member observer.

        Returns:
            Path: Exclusively published archive, adding numeric suffixes on collision.

        Raises:
            OSError: If publication fails for a reason other than an existing name.
        """
        collision_index = 0
        while True:
            collision_suffix = f"_{collision_index}" if collision_index else ""
            zip_name = f"{base_zip_name[:-4]}{collision_suffix}.zip"
            zip_path = backup_path / zip_name
            if zip_path.exists() or zip_path.is_symlink():
                collision_index += 1
                continue
            try:
                return _write_verified_zip_exclusive(zip_path, entries, message_callback, validate=partial(self._validate_written_archive, backup_type=backup_type))
            except FileExistsError:
                if not (zip_path.exists() or zip_path.is_symlink()):
                    raise
                collision_index += 1
