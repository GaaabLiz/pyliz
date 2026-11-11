"""Copy a domain association into its contained snapshot storage destination."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from pylizlib.core.os.snap.copy_strategy import DirectoryCopyStrategy, SequentialFileCopyStrategy
from pylizlib.core.os.snap.integrity import IntegrityManifest
from pylizlib.core.os.snap.storage.tree import assert_no_symlinks

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
    """Copy this association using the configured directory-copy strategy."""
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

    destination.parent.mkdir(parents=True, exist_ok=True)
    if catalogue_target_path.is_symlink() or catalogue_target_path.resolve(strict=False) != target_root:
        raise ValueError(f"Snapshot storage root '{catalogue_target_path}' changed during copy.")
    try:
        if manifest is None and expected_manifest is None:
            selected_strategy.copy_directory(source, destination, progress_callback, message_callback)
        else:
            selected_strategy.copy_directory(
                source,
                destination,
                progress_callback,
                message_callback,
                manifest=manifest,
                expected_manifest=expected_manifest,
            )
    except Exception:
        if destination.is_symlink():
            destination.unlink(missing_ok=True)
        elif destination.exists():
            shutil.rmtree(destination)
        raise
    if destination.is_symlink() or destination.resolve(strict=False) != expected_destination or not destination.is_dir():
        raise ValueError(f"Snapshot directory '{destination}' changed during copy.")
    captured_manifest = manifest if manifest is not None else expected_manifest
    if captured_manifest is not None:
        association.record_captured_content(captured_manifest)
