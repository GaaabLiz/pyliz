"""Association metadata and validation for stored directory copies."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import TYPE_CHECKING

from pylizlib.core.os.snap.copy_strategy import DirectoryCopyStrategy
from pylizlib.core.os.snap.integrity import IntegrityManifest, integrity_manifest_size_mb, validate_integrity_manifest
from pylizlib.core.os.snap.storage.original_paths import normalize_original_path

if TYPE_CHECKING:
    from pylizlib.core.os.snap.domain import SnapDirAssociation


def validate_directory_component(value: str, field_name: str = "directory name", allow_empty: bool = False) -> str:
    """Validate one relative component under the snapshot library's existing rules.

    Args:
        value (str): Component to retain unchanged; separators, colon, NUL, dot/parent,
            absolute paths and an empty value are rejected unless allow_empty permits it.
        field_name (str): Human-readable field label included in validation errors.
        allow_empty (bool): Permit exactly the empty string when True, default False.

    Returns:
        str: The original accepted component, without normalization or sanitization.

    Raises:
        TypeError: If value is not a string.
        ValueError: If the component violates the rules above.

    Notes:
        This is not a complete Windows reserved-name or cross-filesystem filename validator. Whitespace is not
        stripped and names are never silently rewritten.
    """
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string.")
    if allow_empty and value == "":
        return value
    if not value or value in {".", ".."} or "/" in value or "\\" in value or ":" in value or "\x00" in value or Path(value).is_absolute() or Path(value).name != value:
        raise ValueError(f"{field_name} must be a single relative path component: {value!r}.")
    return value


class _AssociationModel:
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

    def __post_init__(self):
        """Validate and normalize without scanning the possibly remote source tree.

        Returns:
            None: No return value.
        """
        self._storage_name = None
        self._storage_id = None
        self._path_initialized = False
        self.validate()

    def record_captured_content(self, manifest: IntegrityManifest) -> None:
        """Retain independent integrity entries and the exact captured content size.

        Args:
            manifest (IntegrityManifest): Complete validated tree manifest, including the
                dot-root directory entry. A missing/None manifest is not an input to this API.

        Returns:
            None: integrity_manifest receives new entry dictionaries and mb_size is recalculated
            from captured file bytes divided by 1024**2, without scanning the original source.

        Raises:
            TypeError: If manifest is not an accepted integrity mapping.
            ValueError: If a path, entry, byte size, hash or required root entry is invalid.
        """
        validate_integrity_manifest(manifest)
        self.integrity_manifest = {path: dict(entry) for path, entry in manifest.items()}
        self.mb_size = integrity_manifest_size_mb(self.integrity_manifest)

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

        # Validate ordering and source identity before any path normalization.
        if type(self.index) is not int:
            raise TypeError("Snapshot directory index must be an integer.")
        if self.index < 0:
            raise ValueError("Snapshot directory index cannot be negative.")
        if not isinstance(self.original_path, str):
            raise TypeError("Snapshot directory original_path must be a string.")
        if not self.original_path or "\x00" in self.original_path:
            raise ValueError("Snapshot directory original_path must be a non-empty path without NUL characters.")
        if not isinstance(self.folder_id, str) or not self.folder_id:
            raise TypeError("Snapshot directory folder_id must be a non-empty string.")

        # Only initial construction may anchor a relative source to the current CWD.
        self.original_path = normalize_original_path(
            self.original_path,
            allow_relative=not self._path_initialized,
        )
        self._path_initialized = True

        # A supplied legacy size is accepted without scanning the source tree.
        if self.mb_size is not None:
            if type(self.mb_size) not in (int, float):
                raise TypeError("Snapshot directory mb_size must be a non-negative number or None.")
            if self.mb_size < 0 or (type(self.mb_size) is float and not math.isfinite(self.mb_size)):
                raise ValueError("Snapshot directory mb_size must be finite and non-negative.")

        # Once captured content exists, its file-byte total is authoritative.
        validate_integrity_manifest(self.integrity_manifest)

        # The captured tree is authoritative; a copied source-size estimate
        # from older metadata must not override the stored content size.
        if self.integrity_manifest is not None:
            self.mb_size = integrity_manifest_size_mb(self.integrity_manifest)

    @classmethod
    def next_index(cls):
        """Increments and returns the class-level index for new directory associations.

        Returns:
            int: The next integer index.
        """
        cls._current_index += 1
        return cls._current_index

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
        self.validate()
        stored_name = getattr(self, "_storage_name", None)
        stored_id = getattr(self, "_storage_id", None)
        if stored_name is not None and stored_id == self.folder_id:
            return validate_directory_component(stored_name, "snapshot association storage name")
        digest = hashlib.sha256(self.folder_id.encode("utf-8")).hexdigest()
        return f"assoc-{digest}"

    @property
    def _legacy_directory_name(self) -> str:
        """Return the index-and-basename name used by snapshots before storage IDs.

        Returns:
            str: Legacy index-basename component; current normal storage names are independent of the index.

        Raises:
            ValueError: A value, path, resource limit or metadata field violates the validation rules described above.
        """
        self.validate()
        basename = Path(self.original_path).name
        if not basename:
            raise ValueError("Snapshot directory original_path must have a final path component.")
        return validate_directory_component(f"{self.index}-{basename}")

    def _set_storage_name(self, storage_name: str) -> None:
        """Retain a physical name loaded from metadata or copied from a clone.

        Args:
            storage_name (str): Persisted physical association-directory component, including accepted legacy names.

        Returns:
            None: No return value.
        """
        self._storage_name = validate_directory_component(storage_name, "snapshot association storage name")
        self._storage_id = self.folder_id

    @staticmethod
    def gen_random(
        source_folder_for_choices: Path,
        folder_id_length: int = 4,
    ) -> "SnapDirAssociation":
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
        from pylizlib.core.os.snap.storage.association import copy_association

        return copy_association(self, catalogue_target_path, progress_callback, message_callback, copy_strategy=copy_strategy, manifest=manifest, expected_manifest=expected_manifest)
