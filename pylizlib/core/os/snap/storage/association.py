"""Copy a domain association into its contained snapshot storage destination."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from pylizlib.core.os.filesystem.entries import entry_exists
from pylizlib.core.os.snap.copy_strategy import DirectoryCopyStrategy, SequentialFileCopyStrategy
from pylizlib.core.os.snap.integrity import IntegrityManifest
from pylizlib.core.os.snap.storage.tree import assert_destination_outside_source, assert_no_symlinks, is_link_or_junction

if TYPE_CHECKING:
    from pylizlib.core.os.snap.domain import SnapDirAssociation


def copy_association(
    association: "SnapDirAssociation",
    catalogue_target_path: Path,
    progress_callback=None,
    message_callback=None,
    *,
    copy_strategy: DirectoryCopyStrategy | None = None,
    manifest: IntegrityManifest | None = None,
    expected_manifest: IntegrityManifest | None = None,
):
    """Copy this association using the configured directory-copy strategy.

    Args:
        association (SnapDirAssociation): Directory association providing stable folder_id, original source and
            stored directory name.
        catalogue_target_path (Path): Storage parent under which this association's physical directory_name is
            copied.
        progress_callback (CopyProgressCallback | None): Optional observer receiving (copied_bytes, total_bytes),
            including terminal empty-tree progress; return values do not cancel copying.
        message_callback (MessageCallback | None): Optional status observer receiving one message string; its
            exceptions propagate according to the calling operation.
        copy_strategy (DirectoryCopyStrategy | None): Directory-copy strategy; None selects the sequential default
            where supported.
        manifest (IntegrityManifest | None): Optional mutable captured-integrity output, replaced only on
            successful copy. expected_manifest can still require verification when this is None.
        expected_manifest (IntegrityManifest | None): Previously captured integrity mapping to verify before
            publishing; None disables this comparison.

    Returns:
        None: No return value.

    Raises:
        TypeError: An argument or mutable model field has a type rejected by this contract.
        ValueError: A value, path, resource limit or metadata field violates the validation rules described above.
        FileExistsError: The final destination already exists or appears before publication; it is left intact.

    Notes:
        The delegate writes inside an exclusively created private workspace. Cleanup owns only that workspace,
        including partial files left by a custom strategy. Existing final destinations are never cleanup targets.
        The output manifest and association metadata are updated only after the completed tree is published.
    """
    source = Path(association.original_path)
    directory_name = association.directory_name
    selected_strategy = copy_strategy or SequentialFileCopyStrategy()
    if not isinstance(selected_strategy, DirectoryCopyStrategy):
        raise TypeError("copy_strategy must implement DirectoryCopyStrategy.")
    assert_no_symlinks(source)

    target_is_junction = getattr(catalogue_target_path, "is_junction", None)
    if catalogue_target_path.is_symlink() or (target_is_junction is not None and target_is_junction()):
        raise ValueError(f"Snapshot storage root '{catalogue_target_path}' cannot be a symbolic link.")
    destination = catalogue_target_path / directory_name
    target_root = catalogue_target_path.resolve(strict=False)
    expected_destination = target_root / directory_name
    resolved_destination = destination.resolve(strict=False)
    if resolved_destination != expected_destination or not resolved_destination.is_relative_to(target_root):
        raise ValueError(f"Snapshot directory destination '{destination}' escapes '{catalogue_target_path}'.")
    assert_destination_outside_source(source, destination)

    destination.parent.mkdir(parents=True, exist_ok=True)
    if is_link_or_junction(catalogue_target_path) or catalogue_target_path.resolve(strict=False) != target_root:
        raise ValueError(f"Snapshot storage root '{catalogue_target_path}' changed during copy.")
    if entry_exists(destination):
        raise FileExistsError(f"Copy destination '{destination}' already exists.")

    # Own a separate staging parent, so delegate failures cannot delete a foreign destination.
    staged_manifest = {} if manifest is not None else None
    with tempfile.TemporaryDirectory(prefix=".association_copy_", dir=catalogue_target_path) as temporary_directory:
        staged = Path(temporary_directory) / directory_name
        if manifest is None and expected_manifest is None:
            selected_strategy.copy_directory(source, staged, progress_callback, message_callback)
        else:
            selected_strategy.copy_directory(
                source,
                staged,
                progress_callback,
                message_callback,
                manifest=staged_manifest,
                expected_manifest=expected_manifest,
            )

        # Recheck the private result and storage identity before publishing any final name.
        assert_no_symlinks(staged)
        expected_staged = target_root / Path(temporary_directory).name / directory_name
        if staged.resolve(strict=False) != expected_staged:
            raise ValueError(f"Snapshot staging directory '{staged}' changed during copy.")
        if is_link_or_junction(catalogue_target_path) or catalogue_target_path.resolve(strict=False) != target_root:
            raise ValueError(f"Snapshot storage root '{catalogue_target_path}' changed during copy.")
        if entry_exists(destination):
            raise FileExistsError(f"Copy destination '{destination}' appeared during copying.")
        staged.rename(destination)

    if destination.is_symlink() or destination.resolve(strict=False) != expected_destination or not destination.is_dir():
        raise ValueError(f"Snapshot directory '{destination}' changed during copy.")
    if manifest is not None:
        manifest.clear()
        manifest.update(staged_manifest or {})
    captured_manifest = manifest if manifest is not None else expected_manifest
    if captured_manifest is not None:
        association.record_captured_content(captured_manifest)
